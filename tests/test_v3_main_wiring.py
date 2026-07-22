"""v3 Task 13：main / pipeline / proactive 宿主接线（RED-first）。

覆盖 plan Task 13 与 design 14.1/14.2/4.3：

- ``__init__`` 造 facade **不做 IO**（不建仓库目录、不落盘）。
- ``initialize()`` 先 acquire epoch 再起 worker；失败只 fail-close v3。
- ``terminate()`` 先 ``begin_shutdown()``，让既有 v2 save drain，再 await v3 shutdown，
  **然后**才走既有通用 task 取消。
- v3 future 绝不进 ``plugin._background_tasks``；v3 身份绝不写 ``event.extra``。
- 终端证据矩阵（design 14.2 + Task 2 真源 4.26.5 事实）：
  FALLBACK→UNKNOWN、全段成功→SPEAK（且只结算一次）、首段/次段失败→UNKNOWN、
  段间取消→UNKNOWN、重复终端回调→只结算一次、SILENT→HOLD、
  ordinary（after_message_sent 不是成功回执）→UNKNOWN、proactive dispatched→REACH。
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

import pytest

import main as main_mod
from sylanne_alpha.v3bridge.actual_action import ActualAction


# --------------------------------------------------------------------------- #
# fake host managers
# --------------------------------------------------------------------------- #


class FakeContext:
    """最小 AstrBot Context 桩：只提供插件 __init__/接线需要的面。"""

    def __init__(self) -> None:
        self.provider_manager = None
        self.sent: list[tuple[str, Any]] = []

    def get_registered_star(self, *a: Any, **k: Any) -> None:
        return None

    def get_using_provider(self, *a: Any, **k: Any) -> None:
        return None

    def get_config(self, *a: Any, **k: Any) -> dict:
        return {}

    def register_web_api(self, *a: Any, **k: Any) -> None:
        return None

    async def send_message(self, origin: str, message: Any) -> None:
        self.sent.append((origin, message))


class FakeEvent:
    """真形态事件桩：extra 走 get_extra/set_extra（与生产同一约定）。"""

    def __init__(self, *, origin: str = "qq:GroupMessage:1", message_id: str = "m-1") -> None:
        self.unified_msg_origin = origin
        self.message_str = "hi"
        self._extras: dict[str, Any] = {}
        self.message_obj = type("MO", (), {"message_id": message_id, "self_id": "bot"})()
        self.platform_meta = type("PM", (), {"name": "qq"})()

    def get_extra(self, key: str, default: Any = None) -> Any:
        return self._extras.get(key, default)

    def set_extra(self, key: str, value: Any) -> None:
        self._extras[key] = value

    def get_platform_name(self) -> str:
        return "qq"

    def get_sender_id(self) -> str:
        return "user-1"

    def get_message_type(self) -> str:
        return "GroupMessage"

    def get_group_id(self) -> str:
        return "1"


async def _build_plugin() -> Any:
    return main_mod.EmotionalStatePlugin(FakeContext(), {})


SESSION_ORIGIN = "qq:GroupMessage:1"


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


# --------------------------------------------------------------------------- #
# 1. facade 存在 + __init__ 不做 IO
# --------------------------------------------------------------------------- #


def test_init_creates_facade_without_io(tmp_path: Path) -> None:
    async def go() -> Any:
        plugin = await _build_plugin()
        facade = getattr(plugin, "_v3_shadow", None)
        assert facade is not None, "__init__ 必须造出 v3 shadow facade"
        # 未 initialize 前：无 runtime、无 counters、无 epoch、不收轮。
        assert facade.runtime is None
        assert facade.counters is None
        assert facade.accepting is False
        assert facade.pending_count == 0
        return facade

    facade = _run(go())
    # facade 构造绝不碰文件系统（同步核对，避免在协程里做阻塞 pathlib 调用）。
    assert not any(tmp_path.iterdir())
    assert facade.runtime is None


def test_source_build_defaults_shadow_disabled() -> None:
    from sylanne_alpha.v3bridge.build_flags import BUILD_CHANNEL, V3_SHADOW_ENABLED

    assert V3_SHADOW_ENABLED is False
    assert BUILD_CHANNEL == "source"


def test_no_v3_selector_in_conf_schema_or_webui() -> None:
    root = Path(__file__).resolve().parents[1]
    schema = (root / "_conf_schema.json").read_text(encoding="utf-8").lower()
    # 注意不能粗暴断言 "shadow" 不出现：跨群货架有合法的 shadow 档。
    # 这里断言的是「没有任何 v3 选择器」——v3 是构建期 flag，绝不可用户可选。
    assert "v3" not in schema
    assert "v3_shadow" not in schema
    assert "shadow_enabled" not in schema
    assert "v3_shadow_enabled" not in schema


# --------------------------------------------------------------------------- #
# 2. 生命周期
# --------------------------------------------------------------------------- #


def test_initialize_acquires_epoch_before_worker_start(tmp_path: Path) -> None:
    async def go() -> None:
        plugin = await _build_plugin()
        facade = plugin._v3_shadow
        facade.enabled = True
        started = await facade.initialize(root=tmp_path / "v3")
        assert started is True
        assert facade.runtime is not None
        assert facade.runtime.epoch is not None
        # epoch 先于 worker：supervisor 拿到的正是 facade 的 epoch。
        assert facade.runtime.supervisor.epoch == facade.runtime.epoch
        assert facade.accepting is True
        await facade.terminate()

    _run(go())


def test_session_identity_survives_plugin_restart(tmp_path: Path) -> None:
    async def go() -> None:
        root = tmp_path / "v3"
        first_plugin = await _build_plugin()
        first = first_plugin._v3_shadow
        first.enabled = True
        assert await first.initialize(root=root)
        first_ref = first._identity.session_ref("qq", SESSION_ORIGIN, session_generation=0)
        await first.terminate()

        second_plugin = await _build_plugin()
        second = second_plugin._v3_shadow
        second.enabled = True
        assert await second.initialize(root=root)
        second_ref = second._identity.session_ref("qq", SESSION_ORIGIN, session_generation=0)
        await second.terminate()

        assert first_ref == second_ref
        assert (root / "session_identity.key").is_file()

    _run(go())


def test_concurrent_initialize_coalesces_one_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from sylanne_alpha.v3bridge import integration

    release = asyncio.Event()
    entered = asyncio.Event()
    constructions = 0

    class SlowRuntime:
        def __init__(self, **_kwargs: Any) -> None:
            nonlocal constructions
            constructions += 1
            self.counters = object()

        async def initialize(self) -> None:
            entered.set()
            await release.wait()

        async def terminate(self) -> None:
            return None

    monkeypatch.setattr(integration, "V3ShadowRuntime", SlowRuntime)

    async def go() -> None:
        plugin = await _build_plugin()
        facade = plugin._v3_shadow
        facade.enabled = True
        first = asyncio.create_task(facade.initialize(root=tmp_path / "v3"))
        await entered.wait()
        second = asyncio.create_task(facade.initialize(root=tmp_path / "v3"))
        await asyncio.sleep(0.05)
        assert constructions == 1
        release.set()
        assert await asyncio.gather(first, second) == [True, True]
        await facade.terminate()

    _run(go())


def test_cancelled_terminate_keeps_one_tracked_cleanup_until_worker_exits() -> None:
    async def go() -> None:
        plugin = await _build_plugin()
        facade = plugin._v3_shadow
        facade.enabled = True
        facade.accepting = True
        entered = asyncio.Event()
        release = asyncio.Event()

        class SlowRuntime:
            counters = object()

            def __init__(self) -> None:
                self.calls = 0

            async def terminate(self) -> None:
                self.calls += 1
                entered.set()
                await release.wait()

        runtime = SlowRuntime()
        facade.runtime = runtime
        first = asyncio.create_task(facade.terminate())
        await entered.wait()
        second = asyncio.create_task(facade.terminate())
        await asyncio.sleep(0)
        assert runtime.calls == 1
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        assert facade.runtime is runtime
        release.set()
        await asyncio.wait_for(second, timeout=2.0)
        assert facade.runtime is None
        assert runtime.calls == 1

    _run(go())


def test_facade_terminate_has_a_bounded_wait_without_cancelling_cleanup() -> None:
    """A wedged v3 runtime must not hold plugin/v2 teardown forever."""

    async def go() -> None:
        plugin = await _build_plugin()
        facade = plugin._v3_shadow
        facade.enabled = True
        facade.accepting = True
        entered = asyncio.Event()
        release = asyncio.Event()

        class WedgedRuntime:
            counters = object()

            def __init__(self) -> None:
                self.calls = 0

            async def terminate(self) -> None:
                self.calls += 1
                entered.set()
                await release.wait()

        runtime = WedgedRuntime()
        facade.runtime = runtime

        await asyncio.wait_for(facade.terminate(timeout=0.05), timeout=0.5)
        await entered.wait()
        assert facade.runtime is runtime
        assert facade._terminate_task is not None and not facade._terminate_task.done()

        release.set()
        await asyncio.wait_for(facade.terminate(timeout=1.0), timeout=1.5)
        assert runtime.calls == 1
        assert facade.runtime is None

    _run(go())


def test_first_live_turn_migrates_before_deferred_offer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from sylanne_alpha.v2core import shadow_snapshot
    from sylanne_alpha.v2core.shadow_snapshot import V2SeedSnapshotV1

    async def freeze(_plugin: object, _session_key: str) -> V2SeedSnapshotV1:
        return V2SeedSnapshotV1(user_bond_ema=0.7, user_hesitation_ema=0.3)

    monkeypatch.setattr(shadow_snapshot, "freeze_seed_snapshot_fallback", freeze)

    async def go() -> None:
        plugin = await _build_plugin()
        facade = plugin._v3_shadow
        facade.enabled = True
        assert await facade.initialize(root=tmp_path / "v3")

        assert not facade.ensure_session(
            plugin=plugin,
            session_key=SESSION_ORIGIN,
            platform_id="qq",
            unified_msg_origin=SESSION_ORIGIN,
        )
        facade.capture_request(
            session_key=SESSION_ORIGIN,
            platform_id="qq",
            unified_msg_origin=SESSION_ORIGIN,
            message_id="m-first",
            text_length=4,
            history_present=False,
            gap_seconds=1.0,
            body=None,
            sender_id="user-1",
            is_group=True,
        )
        facade.settle(
            session_key=SESSION_ORIGIN,
            route_kind="SILENT",
            reply_kind="SILENT",
        )
        await facade.join_private_tasks()
        await facade.runtime.join()

        session_ref = facade._identity.session_ref("qq", SESSION_ORIGIN, session_generation=0)
        loaded = facade.runtime.committer.load_state(session_ref)
        assert loaded is not None
        assert loaded.state.revision >= 1
        assert loaded.base.last_committed_turn_sequence.local_sequence >= 2
        await facade.terminate()

    _run(go())


def test_restart_recovers_corrupt_journal_without_refreezing_v2(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from sylanne_alpha.v2core import shadow_snapshot
    from sylanne_alpha.v2core.shadow_snapshot import V2SeedSnapshotV1
    from sylanne_alpha.v3bridge.session_identity import session_filename_token

    freezes = 0

    async def initial_freeze(_plugin: object, _session_key: str) -> V2SeedSnapshotV1:
        nonlocal freezes
        freezes += 1
        return V2SeedSnapshotV1(user_bond_ema=0.7, user_hesitation_ema=0.3)

    monkeypatch.setattr(shadow_snapshot, "freeze_seed_snapshot_fallback", initial_freeze)

    async def go() -> None:
        root = tmp_path / "v3"
        first_plugin = await _build_plugin()
        first = first_plugin._v3_shadow
        first.enabled = True
        assert await first.initialize(root=root)
        first.ensure_session(
            plugin=first_plugin,
            session_key=SESSION_ORIGIN,
            platform_id="qq",
            unified_msg_origin=SESSION_ORIGIN,
        )
        await first.join_private_tasks()
        session_ref = first._identity.session_ref("qq", SESSION_ORIGIN, session_generation=0)
        assert session_ref is not None
        repository = first.runtime.committer.repository
        pointer = repository._load_pointer(session_filename_token(session_ref))
        assert pointer is not None
        (repository.root / pointer.current_journal).write_bytes(b"corrupt")
        await first.terminate()

        async def forbidden_refreeze(_plugin: object, _session_key: str) -> V2SeedSnapshotV1:
            raise AssertionError("existing v3 state must recover before any v2 refreeze")

        monkeypatch.setattr(shadow_snapshot, "freeze_seed_snapshot_fallback", forbidden_refreeze)
        second_plugin = await _build_plugin()
        second = second_plugin._v3_shadow
        second.enabled = True
        assert await second.initialize(root=root)
        second.ensure_session(
            plugin=second_plugin,
            session_key=SESSION_ORIGIN,
            platform_id="qq",
            unified_msg_origin=SESSION_ORIGIN,
        )
        await second.join_private_tasks()
        assert session_ref in second._ready_sessions
        assert second.runtime.committer.load_state(session_ref) is not None
        assert freezes == 1
        await second.terminate()

    _run(go())


def test_runtime_wires_real_plugin_budget_into_repository_admission(tmp_path: Path) -> None:
    from sylanne_alpha.v3bridge.models import RepositoryAdmissionState

    async def go() -> None:
        plugin_root = tmp_path / "plugin-data"
        plugin_root.mkdir()
        (plugin_root / "legacy.bin").write_bytes(b"x" * 1_000_000)
        plugin = await _build_plugin()
        facade = plugin._v3_shadow
        facade.enabled = True
        assert await facade.initialize(
            root=plugin_root / "v3_shadow",
            supervisor_kwargs={"plugin_cap_bytes": 6_000_000},
        )
        assert facade.runtime.committer.repository.hard_limit_bytes == 3_000_000
        snapshot = await facade.runtime.supervisor._load_snapshot()
        assert snapshot.repository_admission is RepositoryAdmissionState.HARD_STOP
        await facade.terminate()

    _run(go())


def test_initialize_failure_fail_closes_v3_only(tmp_path: Path) -> None:
    async def go() -> None:
        plugin = await _build_plugin()
        facade = plugin._v3_shadow
        facade.enabled = True
        # 只读仓库根：epoch 获取必炸。
        broken = tmp_path / "not-a-dir"
        broken.write_text("occupied", encoding="utf-8")
        started = await facade.initialize(root=broken / "v3")
        assert started is False
        assert facade.runtime is None
        assert facade.enabled is False, "v3 失败必须 fail-close v3 自己"
        assert facade.accepting is False
        # v2 侧完全不受影响：capture/settle 变纯空操作，绝不抛。
        facade.capture_request(
            session_key="s",
            platform_id="qq",
            unified_msg_origin="qq:GroupMessage:1",
            message_id="m-1",
            text_length=3,
            history_present=True,
            gap_seconds=1.0,
            body=None,
        )
        facade.settle(session_key="s", route_kind="SILENT", reply_kind="SILENT")

    _run(go())


def test_initialize_and_terminate_are_idempotent(tmp_path: Path) -> None:
    async def go() -> None:
        plugin = await _build_plugin()
        facade = plugin._v3_shadow
        facade.enabled = True
        assert await facade.initialize(root=tmp_path / "v3") is True
        assert await facade.initialize(root=tmp_path / "v3") is False  # 第二次是 no-op
        await facade.terminate()
        await facade.terminate()
        assert facade.runtime is None

    _run(go())


def test_begin_shutdown_is_sync_and_closes_admission(tmp_path: Path) -> None:
    async def go() -> None:
        plugin = await _build_plugin()
        facade = plugin._v3_shadow
        facade.enabled = True
        await facade.initialize(root=tmp_path / "v3")
        assert facade.accepting is True
        facade.begin_shutdown()  # 同步、不 await
        assert facade.accepting is False
        # 关闸后新捕获一律不进 v3。
        facade.capture_request(
            session_key="s",
            platform_id="qq",
            unified_msg_origin="qq:GroupMessage:1",
            message_id="m-1",
            text_length=3,
            history_present=True,
            gap_seconds=1.0,
            body=None,
        )
        assert facade.pending_count == 0
        await facade.terminate()

    _run(go())


def test_terminate_order_v3_shutdown_before_generic_task_cancel(tmp_path: Path) -> None:
    """terminate(): begin_shutdown → v2 save drain → v3 shutdown → 通用 task 取消。"""

    async def go() -> None:
        plugin = await _build_plugin()
        order: list[str] = []

        facade = plugin._v3_shadow
        facade.enabled = True
        await facade.initialize(root=tmp_path / "v3")

        real_begin = facade.begin_shutdown
        real_terminate = facade.terminate

        def _begin() -> None:
            order.append("v3_begin_shutdown")
            real_begin()

        async def _term() -> None:
            order.append("v3_terminate")
            await real_terminate()

        facade.begin_shutdown = _begin  # type: ignore[method-assign]
        facade.terminate = _term  # type: ignore[method-assign]

        async def _never() -> None:
            try:
                await asyncio.sleep(3600)
            except asyncio.CancelledError:
                order.append("generic_task_cancelled")
                raise

        task = asyncio.get_running_loop().create_task(_never())
        plugin._background_tasks.append(task)
        await asyncio.sleep(0)

        await plugin.terminate()

        assert "v3_begin_shutdown" in order, "terminate 必须先调 begin_shutdown()"
        assert "v3_terminate" in order, "terminate 必须 await v3 shutdown"
        assert "generic_task_cancelled" in order
        assert order.index("v3_begin_shutdown") < order.index("v3_terminate")
        assert order.index("v3_terminate") < order.index("generic_task_cancelled"), (
            "v3 shutdown 必须在既有通用 task 取消【之前】完成"
        )

    _run(go())


def test_v3_future_never_enters_plugin_background_tasks(tmp_path: Path) -> None:
    async def go() -> None:
        plugin = await _build_plugin()
        facade = plugin._v3_shadow
        facade.enabled = True
        await facade.initialize(root=tmp_path / "v3")
        # supervisor 自己有 tracked 任务，但一个都不能出现在插件的 _background_tasks 里。
        assert facade.runtime.supervisor.tracked_task_count >= 1
        assert plugin._background_tasks == []
        await facade.terminate()
        assert plugin._background_tasks == []

    _run(go())


def test_v3_identity_never_written_into_event_extra(tmp_path: Path) -> None:
    async def go() -> None:
        plugin = await _build_plugin()
        facade = plugin._v3_shadow
        facade.enabled = True
        await facade.initialize(root=tmp_path / "v3")
        event = FakeEvent()
        facade.capture_request(
            session_key="s",
            platform_id="qq",
            unified_msg_origin=event.unified_msg_origin,
            message_id="m-1",
            text_length=3,
            history_present=True,
            gap_seconds=1.0,
            body=None,
        )
        assert facade.pending_count == 1
        for key in event._extras:
            assert "v3" not in key.lower()
            assert "shadow" not in key.lower()
        await facade.terminate()

    _run(go())


def test_live_reaction_facts_use_hmac_speaker_equality_and_text_cues(tmp_path: Path) -> None:
    async def go() -> None:
        plugin = await _build_plugin()
        facade = plugin._v3_shadow
        facade.enabled = True
        await facade.initialize(root=tmp_path / "v3")
        offers: list[dict[str, Any]] = []
        facade.runtime.offer_response = lambda **kwargs: offers.append(kwargs)

        def one_turn(message_id: str, sender_id: str) -> None:
            facade.capture_request(
                session_key=SESSION_ORIGIN,
                platform_id="qq",
                unified_msg_origin=SESSION_ORIGIN,
                message_id=message_id,
                text_length=8,
                history_present=True,
                gap_seconds=2.0,
                body=None,
                text_warm=1.25,
                text_cold=0.0,
                text_distress=0.0,
                text_question=True,
                text_exclaim=0.0,
                text_punct=1.25,
                text_valence_cue=1.25,
                text_engagement_cue=0.5,
                sender_id=sender_id,
                is_group=True,
            )
            facade.settle(
                session_key=SESSION_ORIGIN,
                route_kind="SILENT",
                reply_kind="SILENT",
            )

        one_turn("m-1", "alice")
        one_turn("m-2", "alice")
        one_turn("m-3", "bob")

        assert offers[0]["reaction_facts"].same_sender is None
        assert offers[1]["reaction_facts"].same_sender is True
        assert offers[2]["reaction_facts"].same_sender is False
        raw_values = offers[1]["observation"][0]
        assert raw_values[25] == 1.25
        assert raw_values[26] == 0.5
        assert b"alice" not in repr(offers).encode("utf-8")
        await facade.terminate()

    _run(go())


def test_reaction_facts_freeze_at_response_boundary_under_overlapping_turns(
    tmp_path: Path,
) -> None:
    """The later response must compare against the latest *settled* speaker.

    Two host deliveries can overlap for the same v3 session while retaining distinct
    delivery keys.  Freezing ``same_sender`` during request capture makes the second
    delivery compare against stale state; the response boundary is the first point at
    which the previous settled speaker is final.
    """

    async def go() -> None:
        plugin = await _build_plugin()
        facade = plugin._v3_shadow
        facade.enabled = True
        await facade.initialize(root=tmp_path / "v3")
        offers: list[dict[str, Any]] = []
        facade.runtime.offer_response = lambda **kwargs: offers.append(kwargs)

        def capture(delivery_key: str, message_id: str, sender_id: str) -> None:
            facade.capture_request(
                session_key=delivery_key,
                platform_id="qq",
                unified_msg_origin=SESSION_ORIGIN,
                message_id=message_id,
                text_length=4,
                history_present=True,
                gap_seconds=1.0,
                body=None,
                sender_id=sender_id,
                is_group=True,
            )

        # Establish Alice as the previous settled speaker.
        capture("seed", "m-seed", "alice")
        facade.settle(session_key="seed", route_kind="SILENT", reply_kind="SILENT")

        # Both requests arrive before either response settles.  B therefore sees Alice
        # at request time, but A settles Bob before B reaches its response boundary.
        capture("delivery-a", "m-a", "bob")
        capture("delivery-b", "m-b", "alice")
        facade.settle(session_key="delivery-a", route_kind="SILENT", reply_kind="SILENT")
        facade.settle(session_key="delivery-b", route_kind="SILENT", reply_kind="SILENT")

        assert [offer["reaction_facts"].same_sender for offer in offers] == [
            None,
            False,
            False,
        ]
        await facade.terminate()

    _run(go())


def test_local_g2_shadow(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Write the mandatory canonical G2 report only for an explicit target."""

    if "SYLANNE_V3_GATE_REPORT" not in os.environ:
        facade = main_mod._V3ShadowFacade()
        assert facade.write_local_g2_report_from_environment() is None
        return

    from sylanne_alpha.v2core import shadow_snapshot
    from sylanne_alpha.v2core.shadow_snapshot import V2SeedSnapshotV1

    async def freeze_seed(_plugin: object, _session_key: str) -> V2SeedSnapshotV1:
        return V2SeedSnapshotV1()

    monkeypatch.setattr(shadow_snapshot, "freeze_seed_snapshot_fallback", freeze_seed)

    async def go() -> dict[str, Any]:
        plugin = await _build_plugin()
        facade = plugin._v3_shadow
        facade.enabled = True
        assert await facade.initialize(root=tmp_path / "v3")

        facade.ensure_session(
            plugin=plugin,
            session_key=SESSION_ORIGIN,
            platform_id="qq",
            unified_msg_origin=SESSION_ORIGIN,
        )
        facade.capture_request(
            session_key=SESSION_ORIGIN,
            platform_id="qq",
            unified_msg_origin=SESSION_ORIGIN,
            message_id="g2-turn-1",
            text_length=8,
            history_present=False,
            gap_seconds=1.0,
            body=None,
            sender_id="g2-user",
            is_group=True,
        )
        facade.settle(
            session_key=SESSION_ORIGIN,
            route_kind="SILENT",
            reply_kind="SILENT",
        )
        await facade.join_private_tasks()
        await facade.runtime.join()

        report = facade.write_local_g2_report_from_environment()
        assert report is not None
        await facade.terminate()
        return report

    report = _run(go())
    target = Path(os.environ["SYLANNE_V3_GATE_REPORT"])
    assert target.is_file(), "an explicitly requested G2 report must be written"
    loaded = json.loads(target.read_text(encoding="utf-8"))
    assert loaded == report

    from sylanne_alpha.v3bridge.runtime_telemetry import ISOLATION_COUNTER_NAMES
    from sylanne_alpha.v3core.canonical import canonical_sha256

    digest = loaded.pop("report_digest")
    assert digest == canonical_sha256(loaded)
    assert loaded["report_kind"] == "v3_local_shadow_g2_v1"
    assert loaded["source_channel"] in {"grey", "stable"}
    assert loaded["build_channel"] in {"source", "grey", "stable"}
    assert loaded["formula_fingerprint"]["version"]
    assert loaded["formula_fingerprint"]["digest"]
    assert loaded["model_fingerprint"]["revision"]
    assert loaded["runtime_fingerprint_digest"]
    assert loaded["accepted_count"] >= 1
    assert loaded["dropped_count"] >= 0
    assert loaded["correlated_count"] >= 1
    assert set(loaded["isolation_counters"]) == set(ISOLATION_COUNTER_NAMES)
    assert all(value == 0 for value in loaded["isolation_counters"].values())
    assert loaded["passed"] is True


def test_local_g2_shadow_rejects_malformed_explicit_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    facade = main_mod._V3ShadowFacade()
    monkeypatch.setenv("SYLANNE_V3_GATE_REPORT", "  ")
    with pytest.raises(ValueError, match="G2 report path"):
        facade.write_local_g2_report_from_environment()


def test_main_source_has_no_v3_conf_or_extra_key() -> None:
    root = Path(__file__).resolve().parents[1]
    for name in (
        "main.py",
        "sylanne_alpha/llm_request_pipeline.py",
        "sylanne_alpha/llm_response_pipeline.py",
        "sylanne_alpha/v2core/integration.py",
        "sylanne_alpha/proactive_bridge.py",
    ):
        source = (root / name).read_text(encoding="utf-8")
        assert 'set_extra("_syl_v3' not in source
        assert "set_extra('_syl_v3" not in source
        assert "_background_tasks.append(v3" not in source


# --------------------------------------------------------------------------- #
# 3. 终端证据矩阵（通过真接线）
# --------------------------------------------------------------------------- #


async def _facade_with_capture(tmp_path: Path, session_key: str = "s") -> Any:
    plugin = main_mod.EmotionalStatePlugin(FakeContext(), {})
    facade = plugin._v3_shadow
    facade.enabled = True
    await facade.initialize(root=tmp_path / "v3")
    facade.capture_request(
        session_key=session_key,
        platform_id="qq",
        unified_msg_origin="qq:GroupMessage:1",
        message_id="m-1",
        text_length=3,
        history_present=True,
        gap_seconds=1.5,
        body={"warmth": 0.5, "tension": 0.2},
    )
    return plugin, facade


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        # SILENT → HOLD
        ({"route_kind": "SILENT", "reply_kind": "SILENT"}, ActualAction.HOLD),
        # FALLBACK（在有效候选之后）→ UNKNOWN
        (
            {"route_kind": "FALLBACK", "reply_kind": "FALLBACK", "part_count": 1},
            ActualAction.UNKNOWN,
        ),
        # ordinary 4.26.5 输出恒 UNKNOWN：after_message_sent 不是成功回执
        (
            {
                "route_kind": "ORDINARY_TEXT",
                "reply_kind": "SPEAK",
                "part_count": 1,
                "after_message_sent": True,
            },
            ActualAction.UNKNOWN,
        ),
        # 全段成功 → SPEAK
        (
            {
                "route_kind": "SEGMENTED_TEXT",
                "reply_kind": "SPEAK",
                "part_count": 2,
                "all_segments_succeeded": True,
            },
            ActualAction.SPEAK,
        ),
        # 首段失败 / 次段失败 / 段间取消 → UNKNOWN
        (
            {
                "route_kind": "SEGMENTED_TEXT",
                "reply_kind": "SPEAK",
                "part_count": 2,
                "all_segments_succeeded": False,
            },
            ActualAction.UNKNOWN,
        ),
        (
            {
                "route_kind": "SEGMENTED_TEXT",
                "reply_kind": "SPEAK",
                "part_count": 2,
                "all_segments_succeeded": None,
            },
            ActualAction.UNKNOWN,
        ),
        # proactive dispatched=True → REACH
        (
            {"route_kind": "PROACTIVE", "proactive_dispatched": True},
            ActualAction.REACH,
        ),
        (
            {"route_kind": "PROACTIVE", "proactive_dispatched": False},
            ActualAction.UNKNOWN,
        ),
    ],
)
def test_terminal_evidence_matrix(tmp_path: Path, kwargs: dict, expected: ActualAction) -> None:
    async def go() -> None:
        _plugin, facade = await _facade_with_capture(tmp_path)
        facade.settle(session_key="s", **kwargs)
        assert list(facade.settled_actions) == [expected]
        await facade.terminate()

    _run(go())


def test_duplicate_terminal_callback_settles_only_once(tmp_path: Path) -> None:
    async def go() -> None:
        _plugin, facade = await _facade_with_capture(tmp_path)
        for _ in range(3):
            facade.settle(
                session_key="s",
                route_kind="SEGMENTED_TEXT",
                reply_kind="SPEAK",
                part_count=2,
                all_segments_succeeded=True,
            )
        assert list(facade.settled_actions) == [ActualAction.SPEAK], "重复终端回调只能结算一次"
        assert facade.pending_count == 0
        await facade.terminate()

    _run(go())


def test_fallback_after_valid_candidate_is_unknown_and_blocks_later_speak(
    tmp_path: Path,
) -> None:
    """FALLBACK 在有效候选之后结算 UNKNOWN；后到的 SPEAK 不得改写已结算的轮。"""

    async def go() -> None:
        _plugin, facade = await _facade_with_capture(tmp_path)
        facade.settle(session_key="s", route_kind="FALLBACK", reply_kind="FALLBACK", part_count=1)
        facade.settle(
            session_key="s",
            route_kind="SEGMENTED_TEXT",
            reply_kind="SPEAK",
            part_count=2,
            all_segments_succeeded=True,
        )
        assert list(facade.settled_actions) == [ActualAction.UNKNOWN]
        await facade.terminate()

    _run(go())


def test_settle_without_capture_is_a_noop(tmp_path: Path) -> None:
    async def go() -> None:
        plugin = main_mod.EmotionalStatePlugin(FakeContext(), {})
        facade = plugin._v3_shadow
        facade.enabled = True
        await facade.initialize(root=tmp_path / "v3")
        facade.settle(session_key="never-captured", route_kind="SILENT", reply_kind="SILENT")
        assert list(facade.settled_actions) == []
        await facade.terminate()

    _run(go())


class FakeRequest:
    def __init__(self) -> None:
        self.system_prompt = "PERSONA"
        self.prompt = "hi"
        self.contexts = [
            {"role": "user", "content": "a"},
            {"role": "assistant", "content": "b"},
        ]


def test_capture_fires_at_the_real_request_boundary(tmp_path: Path) -> None:
    """真生产路径：`_process_llm_request_final` 走完，Step 4.5 必须冻结这一轮。"""

    async def go() -> None:
        plugin = main_mod.EmotionalStatePlugin(FakeContext(), {})
        facade = plugin._v3_shadow
        facade.enabled = True
        await facade.initialize(root=tmp_path / "v3")
        event, request = FakeEvent(), FakeRequest()
        await plugin._llm_request_pipeline._process_llm_request_final(
            event, request, "hi there", "qq:GroupMessage:1", False, False, False
        )
        assert facade.pending_count == 1, "请求边界必须在 final prompt assembly 之前捕获这一轮"
        # 捕获点在 assembly 之前，但 assembly 照常发生（v3 没挡住 v2）。
        assert request.system_prompt.startswith("PERSONA")
        await facade.terminate()

    _run(go())


def test_request_boundary_projects_v2_lexicon_cues_without_raw_text(tmp_path: Path) -> None:
    async def go() -> None:
        plugin = main_mod.EmotionalStatePlugin(FakeContext(), {})
        facade = plugin._v3_shadow
        facade.enabled = True
        await facade.initialize(root=tmp_path / "v3")
        event, request = FakeEvent(), FakeRequest()
        await plugin._llm_request_pipeline._process_llm_request_final(
            event,
            request,
            "抱抱你吗？",
            SESSION_ORIGIN,
            False,
            False,
            False,
        )

        pending = next(iter(facade._pending.values()))
        raw_values = pending.observation[0]
        assert raw_values[19] > 0.0
        assert raw_values[22] == 1.0
        assert raw_values[25] > 0.0
        assert raw_values[26] > 0.0
        assert "抱抱你吗" not in repr(pending.observation)
        await facade.terminate()

    _run(go())


def test_disabled_v3_never_imports_or_scans_lexicon(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from sylanne_alpha.v2core import integration, lexicon

    async def no_v2_request(*_args: Any, **_kwargs: Any) -> None:
        return None

    def forbidden_read(_text: str) -> Any:
        raise AssertionError("disabled v3 must not scan text")

    monkeypatch.setattr(integration, "apply_v2core_request", no_v2_request)
    monkeypatch.setattr(lexicon, "read_signals", forbidden_read)

    async def go() -> None:
        plugin = await _build_plugin()
        assert plugin._v3_shadow.accepting is False
        event, request = FakeEvent(), FakeRequest()
        await plugin._llm_request_pipeline._process_llm_request_final(
            event,
            request,
            "关闭时不应扫描",
            SESSION_ORIGIN,
            False,
            False,
            False,
        )
        assert request.system_prompt.startswith("PERSONA")

    _run(go())


async def _prompt_bytes(*, enabled: bool, root: Path | None) -> tuple[bytes, bytes]:
    """跑一遍真 prompt 组装路径，回传 (system_prompt, contexts) 的字节。

    每次运行前把全局 random 播成同一个种子：v2 的 [心象] 注入本身带概率分支
    （v2core/integration.py 的 _NIGHT_WAKE_CUE_PROB=0.25，以及 variant_pool.choose
    的变体轮换），不控随机就【连 v2 自己两次跑都不逐字节相同】——那样的相等断言是
    在赌骰子，既证不出 v3 无害，也会随机诈红。播种之后差异就只可能来自 v3。
    """

    import random

    random.seed(20260715)
    plugin = main_mod.EmotionalStatePlugin(FakeContext(), {})
    facade = plugin._v3_shadow
    facade.enabled = enabled
    if enabled:
        assert root is not None
        assert await facade.initialize(root=root) is True
    event, request = FakeEvent(), FakeRequest()
    await plugin._llm_request_pipeline._process_llm_request_final(
        event, request, "hi there", "qq:GroupMessage:1", False, False, False
    )
    if enabled:
        assert facade.pending_count == 1, "开启时这一轮必须被捕获（否则相等是空证）"
    await facade.terminate()
    return (
        str(request.system_prompt).encode("utf-8"),
        repr(request.contexts).encode("utf-8"),
    )


def test_request_boundary_prompt_baseline_is_reproducible(tmp_path: Path) -> None:
    """基线自证：播种后两次 disabled 运行必须逐字节相同，下面的相等才有意义。"""

    async def go() -> None:
        first = await _prompt_bytes(enabled=False, root=None)
        second = await _prompt_bytes(enabled=False, root=None)
        assert first == second

    _run(go())


def test_request_boundary_prompt_is_byte_identical_with_shadow_on(tmp_path: Path) -> None:
    """默认关 vs 开启：真 prompt 组装路径产出的 system_prompt/contexts 逐字节相同。"""

    async def go() -> None:
        off_prompt, off_contexts = await _prompt_bytes(enabled=False, root=None)
        on_prompt, on_contexts = await _prompt_bytes(enabled=True, root=tmp_path / "v3")
        assert off_prompt == on_prompt, "开启 v3 后 final system_prompt 必须逐字节相同"
        assert off_contexts == on_contexts, "开启 v3 后 req.contexts 必须逐字节相同"

    _run(go())


def test_segmented_dispatch_settles_speak_only_on_full_success(tmp_path: Path) -> None:
    """真生产路径：`_dispatch_segmented_parts` 全段发完才结算 SPEAK。"""

    async def go() -> None:
        plugin, facade = await _facade_with_capture(tmp_path, session_key="qq:GroupMessage:1")
        parts = [{"text": "a", "delay_before_seconds": 0}, {"text": "b", "delay_before_seconds": 0}]
        await plugin._llm_response_pipeline._dispatch_segmented_parts(
            "qq:GroupMessage:1", parts, session_key="qq:GroupMessage:1"
        )
        assert plugin.context.sent == [
            ("qq:GroupMessage:1", plugin.context.sent[0][1]),
            ("qq:GroupMessage:1", plugin.context.sent[1][1]),
        ]
        assert list(facade.settled_actions) == [ActualAction.SPEAK]
        await facade.terminate()

    _run(go())


def test_segmented_dispatch_first_segment_failure_is_unknown(tmp_path: Path) -> None:
    async def go() -> None:
        plugin, facade = await _facade_with_capture(tmp_path, session_key="qq:GroupMessage:1")

        async def boom(origin: str, message: Any) -> None:
            raise RuntimeError("send failed")

        plugin.context.send_message = boom  # type: ignore[method-assign]
        parts = [{"text": "a", "delay_before_seconds": 0}, {"text": "b", "delay_before_seconds": 0}]
        with pytest.raises(RuntimeError):
            await plugin._llm_response_pipeline._dispatch_segmented_parts(
                "qq:GroupMessage:1", parts, session_key="qq:GroupMessage:1"
            )
        assert list(facade.settled_actions) == [ActualAction.UNKNOWN]
        assert plugin._store.unfinished_replies.get("qq:GroupMessage:1") == "ab"
        await facade.terminate()

    _run(go())


def test_segmented_dispatch_second_segment_failure_is_unknown(tmp_path: Path) -> None:
    async def go() -> None:
        plugin, facade = await _facade_with_capture(tmp_path, session_key="qq:GroupMessage:1")
        calls: list[int] = []

        async def boom_on_second(origin: str, message: Any) -> None:
            calls.append(1)
            if len(calls) >= 2:
                raise RuntimeError("second segment failed")

        plugin.context.send_message = boom_on_second  # type: ignore[method-assign]
        parts = [{"text": "a", "delay_before_seconds": 0}, {"text": "b", "delay_before_seconds": 0}]
        with pytest.raises(RuntimeError):
            await plugin._llm_response_pipeline._dispatch_segmented_parts(
                "qq:GroupMessage:1", parts, session_key="qq:GroupMessage:1"
            )
        assert list(facade.settled_actions) == [ActualAction.UNKNOWN]
        assert plugin._store.unfinished_replies.get("qq:GroupMessage:1") == "b"
        await facade.terminate()

    _run(go())


def test_segmented_dispatch_cancelled_before_first_send_keeps_full_reply(
    tmp_path: Path,
) -> None:
    async def go() -> None:
        plugin, facade = await _facade_with_capture(
            tmp_path,
            session_key="qq:GroupMessage:1",
        )
        parts = [{"text": "整条都还没发", "delay_before_seconds": 30}]
        task = asyncio.create_task(
            plugin._llm_response_pipeline._dispatch_segmented_parts(
                "qq:GroupMessage:1",
                parts,
                session_key="qq:GroupMessage:1",
            )
        )
        await asyncio.sleep(0.05)

        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert plugin.context.sent == []
        assert (
            plugin._store.unfinished_replies.get("qq:GroupMessage:1")
            == "整条都还没发"
        )
        await facade.terminate()

    _run(go())


def test_afterthought_dispatch_never_settles_the_next_turn(tmp_path: Path) -> None:
    """红队 F1 回归：补刀复用同一 session_key，但绝不能认领下一轮的待结算捕获。

    真时序：第 N 轮回复发完（已结算）→ 第 N+1 轮进来（新捕获落在同一个 key）→
    20-180s 后补刀才发。补刀若按普通投递结算，就会把第 N+1 轮的 handle 顶掉、
    按补刀的 part_count 记成 SPEAK，而第 N+1 轮真正的终端证据反而被丢弃。
    """

    async def go() -> None:
        plugin, facade = await _facade_with_capture(tmp_path, session_key=SESSION_ORIGIN)
        pipeline = plugin._llm_response_pipeline
        parts = [{"text": "a", "delay_before_seconds": 0}]

        # 第 N 轮：正常投递 → 结算 SPEAK，pending 清空。
        await pipeline._dispatch_segmented_parts(SESSION_ORIGIN, parts, session_key=SESSION_ORIGIN)
        assert list(facade.settled_actions) == [ActualAction.SPEAK]
        assert facade.pending_count == 0

        # 第 N+1 轮进来：同一个 key 上落了新的捕获。
        facade.capture_request(
            session_key=SESSION_ORIGIN,
            platform_id="qq",
            unified_msg_origin=SESSION_ORIGIN,
            message_id="m-2",
            text_length=3,
            history_present=True,
            gap_seconds=1.0,
            body=None,
        )
        assert facade.pending_count == 1

        # 补刀（settle_v3=False）：v2 照常发，但绝不碰第 N+1 轮的 pending。
        await pipeline._dispatch_segmented_parts(
            SESSION_ORIGIN, parts, session_key=SESSION_ORIGIN, settle_v3=False
        )
        assert list(facade.settled_actions) == [ActualAction.SPEAK], "补刀不得再结算一次"
        assert facade.pending_count == 1, "第 N+1 轮必须还在，等它自己的终端证据"
        await facade.terminate()

    _run(go())


def test_stale_cancel_never_settles_the_turn_that_replaced_it(tmp_path: Path) -> None:
    """红队 F1-residual 回归：迟到的终端回调不得结算顶替它的那一轮。

    真时序（llm_request_pipeline 收到新请求会 cancel 掉旧分段任务）：
      第 N 轮分段在飞 → 第 N+1 轮进来，Step 4.5 的捕获顶掉 _pending[K]
      → 第 N 轮的 CancelledError 处理器【这时才】跑到结算。
    没有栅栏令牌的话，第 N 轮的取消会把第 N+1 轮结算成 UNKNOWN，而第 N+1 轮真正的
    终端证据反而被丢掉。这里刻意把顺序排成最坏情况（捕获先于取消处理器）。
    """

    async def go() -> None:
        plugin, facade = await _facade_with_capture(tmp_path, session_key=SESSION_ORIGIN)
        token_n = facade.pending_token(SESSION_ORIGIN)
        assert token_n is not None

        parts = [
            {"text": "a", "delay_before_seconds": 0},
            {"text": "b", "delay_before_seconds": 30},
        ]
        task = asyncio.get_running_loop().create_task(
            plugin._llm_response_pipeline._dispatch_segmented_parts(
                SESSION_ORIGIN, parts, session_key=SESSION_ORIGIN
            )
        )
        await asyncio.sleep(0.05)  # 第 N 轮已发出第一段，正卡在段间 sleep

        # 第 N+1 轮抢先落在同一个 key 上（模拟 cancel 送达之前捕获就跑完了）。
        facade.capture_request(
            session_key=SESSION_ORIGIN,
            platform_id="qq",
            unified_msg_origin=SESSION_ORIGIN,
            message_id="m-2",
            text_length=3,
            history_present=True,
            gap_seconds=1.0,
            body=None,
        )
        token_n1 = facade.pending_token(SESSION_ORIGIN)
        assert token_n1 is not None and token_n1 != token_n, "新一轮必须拿到新令牌"

        # 现在第 N 轮才被取消 —— 它带的是 token_n，对不上 token_n1，必须放手。
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert list(facade.settled_actions) == [], "过期的取消不得结算任何一轮"
        assert facade.pending_token(SESSION_ORIGIN) == token_n1, "第 N+1 轮必须原封不动"
        assert facade.pending_count == 1

        # 第 N+1 轮仍然能被它自己的终端证据正常结算。
        facade.settle(
            session_key=SESSION_ORIGIN,
            route_kind="SILENT",
            reply_kind="SILENT",
            token=token_n1,
        )
        assert list(facade.settled_actions) == [ActualAction.HOLD]
        await facade.terminate()

    _run(go())


def test_stale_token_is_rejected_but_matching_token_settles(tmp_path: Path) -> None:
    """栅栏令牌的正反面：对不上就放手，对得上就照常结算（防"靠瘫痪换绿"）。"""

    async def go() -> None:
        _plugin, facade = await _facade_with_capture(tmp_path, session_key=SESSION_ORIGIN)
        token = facade.pending_token(SESSION_ORIGIN)
        assert token is not None

        facade.settle(
            session_key=SESSION_ORIGIN,
            route_kind="SILENT",
            reply_kind="SILENT",
            token=token + 999,  # 过期令牌
        )
        assert list(facade.settled_actions) == [], "过期令牌必须放手"
        assert facade.pending_count == 1, "放手不等于丢掉这轮"

        facade.settle(
            session_key=SESSION_ORIGIN,
            route_kind="SILENT",
            reply_kind="SILENT",
            token=token,  # 正确令牌
        )
        assert list(facade.settled_actions) == [ActualAction.HOLD]
        assert facade.pending_count == 0
        await facade.terminate()

    _run(go())


def test_fire_afterthought_passes_settle_v3_false() -> None:
    """F1 接线自证：补刀路径必须显式关掉 v3 结算（防以后有人删掉这个参数）。"""

    root = Path(__file__).resolve().parents[1]
    source = (root / "sylanne_alpha/llm_response_pipeline.py").read_text(encoding="utf-8")
    assert "settle_v3: bool = True" in source
    assert "settle_v3=False" in source
    assert source.count("if settle_v3:") == 3, "三条终端路径都要受 settle_v3 门控"


def test_plugin_wrapper_forwards_settle_v3(tmp_path: Path) -> None:
    """F1 补漏：插件层的转发壳必须原样传 settle_v3，不能吞掉。"""

    async def go() -> None:
        plugin, facade = await _facade_with_capture(tmp_path, session_key=SESSION_ORIGIN)
        parts = [{"text": "a", "delay_before_seconds": 0}]
        # 经插件转发壳走补刀式投递：v2 照发，但绝不结算。
        await plugin._dispatch_segmented_parts(
            SESSION_ORIGIN, parts, session_key=SESSION_ORIGIN, settle_v3=False
        )
        assert plugin.context.sent, "v2 必须照常发出去"
        assert list(facade.settled_actions) == [], "转发壳吞掉 settle_v3 就会重开 F1"
        assert facade.pending_count == 1
        # 默认仍然结算（不能为了挡住上面把正常路也关死）。
        await plugin._dispatch_segmented_parts(
            SESSION_ORIGIN, parts, session_key=SESSION_ORIGIN
        )
        assert list(facade.settled_actions) == [ActualAction.SPEAK]
        await facade.terminate()

    _run(go())


def test_terminate_never_abandons_a_live_runtime_worker(tmp_path: Path) -> None:
    """关停不得用超时遗弃仍存活的私有 executor/runtime。"""

    async def go() -> None:
        plugin = await _build_plugin()
        facade = plugin._v3_shadow
        facade.enabled = True
        await facade.initialize(root=tmp_path / "v3")

        release = asyncio.Event()

        class _SlowRuntime:
            async def terminate(self) -> None:
                await release.wait()

        real_runtime = facade.runtime
        facade.runtime = _SlowRuntime()
        shutdown = asyncio.create_task(facade.terminate())
        await asyncio.sleep(0.05)
        assert not shutdown.done(), "runtime 仍存活时 facade 不得假装 terminate 完成"
        release.set()
        await asyncio.wait_for(shutdown, timeout=2.0)
        assert facade.runtime is None
        await real_runtime.terminate()

    _run(go())


def test_executor_shutdown_does_not_block_the_event_loop() -> None:
    """F3 接线自证：私有线程池的 join 必须让出事件循环（不能直接同步 join）。"""

    root = Path(__file__).resolve().parents[1]
    source = (root / "sylanne_alpha/v3bridge/shadow_supervisor.py").read_text(encoding="utf-8")
    assert "await self._bounded_shutdown_step(" in source
    assert "self._executor.shutdown," in source
    assert "\n            self._executor.shutdown(wait=True, cancel_futures=True)" not in source


def test_context_class_is_frozen_per_turn_kind(tmp_path: Path) -> None:
    """红队 F2 回归：主动轮/环境轮不得被一律冻成 ADDRESSED。"""

    from sylanne_alpha.v3core.contracts import TurnContextClass

    async def go() -> None:
        plugin = await _build_plugin()
        facade = plugin._v3_shadow
        facade.enabled = True
        await facade.initialize(root=tmp_path / "v3")

        cases = [
            ({"addressed": True, "proactive": False}, TurnContextClass.ADDRESSED),
            ({"addressed": False, "proactive": False}, TurnContextClass.AMBIENT),
            ({"addressed": False, "proactive": True}, TurnContextClass.PROACTIVE),
            # proactive 压过 addressed：主动轮就是主动轮。
            ({"addressed": True, "proactive": True}, TurnContextClass.PROACTIVE),
        ]
        for index, (kwargs, expected) in enumerate(cases):
            key = f"s-{index}"
            facade.capture_request(
                session_key=key,
                platform_id="qq",
                unified_msg_origin=f"qq:GroupMessage:{index}",
                message_id=f"m-{index}",
                text_length=3,
                history_present=True,
                gap_seconds=1.0,
                body=None,
                **kwargs,
            )
            assert facade.has_pending(key), f"case {index} 必须被捕获"
            assert facade._pending[key].context is expected, f"case {index} 上下文类别错"
        await facade.terminate()

    _run(go())


def test_proactive_inflight_drives_proactive_context() -> None:
    """F2 接线自证：请求边界必须问 proactive bridge 「此刻是否有主动发言在飞」。"""

    root = Path(__file__).resolve().parents[1]
    request_src = (root / "sylanne_alpha/llm_request_pipeline.py").read_text(encoding="utf-8")
    bridge_src = (root / "sylanne_alpha/proactive_bridge.py").read_text(encoding="utf-8")
    assert "proactive=_v3_proactive_of(p, session_key)" in request_src
    assert "addressed=_v3_addressed_of(event)" in request_src
    assert "is_at_or_wake_command" in request_src, "点名判定要读框架自己的属性"
    assert "def is_dispatch_inflight" in bridge_src


def test_proactive_bridge_inflight_accessor_is_read_only() -> None:
    async def go() -> None:
        plugin = await _build_plugin()
        bridge = plugin._proactive_bridge
        assert bridge.is_dispatch_inflight("nobody") is False
        bridge._inflight_dispatch.add("qq:GroupMessage:9")
        assert bridge.is_dispatch_inflight("qq:GroupMessage:9") is True
        # 只读：问过之后在飞集合不变。
        assert bridge._inflight_dispatch == {"qq:GroupMessage:9"}
        assert bridge.is_dispatch_inflight("") is False

    _run(go())


def test_ordinary_settle_yields_to_proactive_turn(tmp_path: Path) -> None:
    """红队 F2-follow-on 回归：主动轮只能由 REACH 结算。

    大饼的 check_and_chat 也走 RespondStage，after_message_sent 照样响；ordinary 记账
    若抢先认领，proactive_bridge 的 REACH 就永远落不到（这一轮会被记成 UNKNOWN）。
    """

    async def go() -> None:
        plugin = await _build_plugin()
        facade = plugin._v3_shadow
        facade.enabled = True
        await facade.initialize(root=tmp_path / "v3")
        facade.capture_request(
            session_key=SESSION_ORIGIN,
            platform_id="qq",
            unified_msg_origin=SESSION_ORIGIN,
            message_id="m-1",
            text_length=3,
            history_present=False,
            gap_seconds=1.0,
            body=None,
            addressed=False,
            proactive=True,
        )
        assert facade.pending_is_proactive(SESSION_ORIGIN) is True

        # ordinary 记账必须让路，不得认领这一轮。
        plugin._v3_settle_ordinary(FakeEvent(origin=SESSION_ORIGIN))
        assert list(facade.settled_actions) == [], "主动轮不得被 ordinary 记账抢走"
        assert facade.pending_count == 1

        # REACH 才是这一轮的终端证据。
        plugin._proactive_bridge._v3_settle_reach(SESSION_ORIGIN, SESSION_ORIGIN)
        assert list(facade.settled_actions) == [ActualAction.REACH]
        await facade.terminate()

    _run(go())


def test_ordinary_settle_yields_when_segmented_task_inflight(tmp_path: Path) -> None:
    """红队 F4 回归：接管标记写失败时，在飞的分段任务是兜底判据。"""

    async def go() -> None:
        plugin, facade = await _facade_with_capture(tmp_path, session_key=SESSION_ORIGIN)

        async def _still_sending() -> None:
            await asyncio.sleep(3600)

        task = asyncio.get_running_loop().create_task(_still_sending())
        plugin._store.segmented_tasks.set(SESSION_ORIGIN, task)
        try:
            # extra 标记刻意【不写】：模拟 set_extra 失败的降级路径。
            event = FakeEvent(origin=SESSION_ORIGIN)
            assert event.get_extra("_syl_realtime_takeover", None) is None
            plugin._v3_settle_ordinary(event)
            assert list(facade.settled_actions) == [], "有在飞分段任务时 ordinary 不得抢先结算"
            assert facade.pending_count == 1
        finally:
            task.cancel()
        await facade.terminate()

    _run(go())


def test_ordinary_settle_still_fires_for_a_plain_turn(tmp_path: Path) -> None:
    """让路逻辑不能把正常 ordinary 轮也挡掉（否则上面两条是靠瘫痪换来的绿）。"""

    async def go() -> None:
        plugin, facade = await _facade_with_capture(tmp_path, session_key=SESSION_ORIGIN)
        assert facade.pending_is_proactive(SESSION_ORIGIN) is False
        assert plugin._store.segmented_tasks.get(SESSION_ORIGIN) is None
        plugin._v3_settle_ordinary(FakeEvent(origin=SESSION_ORIGIN))
        assert list(facade.settled_actions) == [ActualAction.UNKNOWN]
        await facade.terminate()

    _run(go())


def test_segmented_dispatch_cancelled_between_segments_is_unknown(tmp_path: Path) -> None:
    async def go() -> None:
        plugin, facade = await _facade_with_capture(tmp_path, session_key="qq:GroupMessage:1")
        parts = [
            {"text": "a", "delay_before_seconds": 0},
            {"text": "b", "delay_before_seconds": 30},
        ]
        task = asyncio.get_running_loop().create_task(
            plugin._llm_response_pipeline._dispatch_segmented_parts(
                "qq:GroupMessage:1", parts, session_key="qq:GroupMessage:1"
            )
        )
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert list(facade.settled_actions) == [ActualAction.UNKNOWN], "段间取消 → UNKNOWN"
        await facade.terminate()

    _run(go())
