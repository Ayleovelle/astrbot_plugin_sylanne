from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, replace
from pathlib import Path

import astrbot
import pytest

from sylanne_alpha.v2core.shadow_snapshot import V2ResponseCandidateV1
from sylanne_alpha.v3bridge.actual_action import ActualAction, project_actual_action
from sylanne_alpha.v3bridge.session_identity import SessionIdentityKey
from sylanne_alpha.v3bridge.turn_registry import TurnRegistry


ASTRBOT_VERSION = "4.26.5"
ASTRBOT_SOURCE_COMMIT = "39090a74bae58608c7f0b758e75b4c0cd71898e8"
PINNED_SHA256 = {
    "__init__.py": "966101b63d93472145fbb924317bbf903a7707527421b1d995450fc8832811ef",
    "core/astr_agent_hooks.py": "accd70ee25c31732f4915f3dfb5cedfd5c1ca2e2890c4d8fa070eb4c74d12317",
    "core/pipeline/process_stage/method/agent_sub_stages/internal.py": "1d12b1e69e8ccc05a39370f028f17cd5716d40a3d7ec5bd4836323cbb0bf1e0d",
    "core/pipeline/process_stage/method/agent_sub_stages/third_party.py": "69fffca5916fe2526aa7ea56537bc4a39f99ef2d8f68e7427f3790d69f768e35",
    "core/pipeline/result_decorate/stage.py": "0d994ef50d6501b3bc029d6306c7cb58e9d1683cb186af0493922b17e7502a2a",
    "core/pipeline/respond/stage.py": "10b36196a67cad83e52b68890e942e5fc5f71ceb66e11918656266610c9438e6",
}


@dataclass(frozen=True, slots=True)
class _HookCaseResult:
    actual_action: ActualAction
    captures: int
    terminal_attempts: int
    accepted_terminal_claims: int
    projected_call_count: int


def _astrbot_root() -> Path:
    configured = os.environ.get("ASTRBOT_SRC")
    root = Path(configured) if configured else Path(astrbot.__file__).resolve().parent
    assert root.is_dir(), f"ASTRBOT_SRC is not a directory: {root}"
    return root


def _source(relative: str) -> str:
    return (_astrbot_root() / relative).read_text(encoding="utf-8")


def _sha256(relative: str) -> str:
    return hashlib.sha256((_astrbot_root() / relative).read_bytes()).hexdigest()


def _ordinary_candidate() -> V2ResponseCandidateV1:
    return V2ResponseCandidateV1(
        route_kind="ORDINARY_TEXT",
        reply_kind="SPEAK",
        part_count=1,
        correlation_proven=True,
        after_message_sent=True,
    )


def _candidate_for_case(case: str) -> V2ResponseCandidateV1:
    candidate = _ordinary_candidate()
    if case == "ordinary":
        pass
    elif case == "silent":
        candidate = V2ResponseCandidateV1(
            route_kind="SILENT",
            reply_kind="SILENT",
            correlation_proven=True,
        )
    elif case == "fallback":
        candidate = V2ResponseCandidateV1(
            route_kind="FALLBACK",
            reply_kind="FALLBACK",
            part_count=1,
            correlation_proven=True,
        )
    elif case == "tool_loop":
        candidate = replace(candidate, route_kind="TOOL", after_message_sent=False)
    elif case == "repeated_provider_response":
        pass
    elif case == "streaming":
        candidate = replace(candidate, route_kind="STREAMING", after_message_sent=False)
    elif case == "media":
        candidate = replace(candidate, route_kind="MEDIA", after_message_sent=False)
    elif case == "provider_exception":
        candidate = V2ResponseCandidateV1(
            route_kind="PROVIDER_FAILURE",
            reply_kind=None,
            correlation_proven=True,
        )
    elif case == "unaddressed_group":
        candidate = replace(
            candidate,
            route_kind="UNMATCHED",
            correlation_proven=False,
            after_message_sent=False,
        )
    elif case == "partial_send":
        candidate = replace(
            candidate,
            route_kind="SEGMENTED_TEXT",
            part_count=2,
            after_message_sent=False,
            all_segments_succeeded=False,
        )
    elif case == "cancelled_segmented_send":
        candidate = replace(
            candidate,
            route_kind="DELIVERY_FAILURE",
            part_count=2,
            after_message_sent=False,
            all_segments_succeeded=None,
        )
    elif case == "segmented_success":
        candidate = replace(
            candidate,
            route_kind="SEGMENTED_TEXT",
            part_count=2,
            after_message_sent=False,
            all_segments_succeeded=True,
        )
    elif case == "proactive_dispatched":
        candidate = V2ResponseCandidateV1(
            route_kind="PROACTIVE",
            reply_kind=None,
            proactive_dispatched=True,
            correlation_proven=True,
        )
    else:
        raise AssertionError(f"unknown hook case: {case}")
    return candidate


def _run_hook_case(case: str) -> _HookCaseResult:
    candidate = _candidate_for_case(case)
    identity = SessionIdentityKey(key_id="integration-v1", secret=b"identity" * 4)
    registry = TurnRegistry(
        plugin_instance_id="integration-plugin",
        correlation_secret=b"correlation" * 4,
        writer_epoch=1,
    )
    origin = "" if case == "unaddressed_group" else "umo-1"
    session_ref = identity.session_ref("qq", origin, session_generation=0)
    handle = registry.capture_request(
        session_ref=session_ref,
        bridge_request_nonce="request-1",
        request_attempt=0,
        platform_id="qq",
        unified_msg_origin=origin,
        message_id="message-1",
        now=1.0,
    )
    terminal_attempts = 2 if case == "repeated_provider_response" else 1
    actual_action = ActualAction.UNMATCHED_RESPONSE
    projected_call_count = 0
    for attempt in range(terminal_attempts):
        accepted = registry.claim_response(
            handle=handle,
            platform_id="qq",
            unified_msg_origin=origin,
            message_id="message-1",
            now=2.0 + attempt,
        )
        if accepted:
            actual_action = project_actual_action(candidate)
            projected_call_count += 1
        else:
            actual_action = ActualAction.UNMATCHED_RESPONSE
    stats = registry.stats()
    return _HookCaseResult(
        actual_action=actual_action,
        captures=stats.captures,
        terminal_attempts=stats.terminal_attempts,
        accepted_terminal_claims=stats.accepted_terminal_claims,
        projected_call_count=projected_call_count,
    )


def test_real_astrbot_source_is_the_pinned_v4265_flow() -> None:
    assert getattr(astrbot, "__version__", None) == ASTRBOT_VERSION
    actual_hashes = {relative: _sha256(relative) for relative in PINNED_SHA256}
    assert actual_hashes == PINNED_SHA256, (
        f"AstrBot source differs from pinned commit {ASTRBOT_SOURCE_COMMIT}"
    )


def test_real_source_orders_request_response_decorate_and_delivery_hooks() -> None:
    internal = _source("core/pipeline/process_stage/method/agent_sub_stages/internal.py")
    third_party = _source("core/pipeline/process_stage/method/agent_sub_stages/third_party.py")
    hooks = _source("core/astr_agent_hooks.py")
    decorate = _source("core/pipeline/result_decorate/stage.py")
    respond = _source("core/pipeline/respond/stage.py")

    request_hook = internal.index("EventType.OnLLMRequestEvent")
    register_call = internal.index(
        "register_active_runner(event.unified_msg_origin, agent_runner)",
        request_hook,
    )
    assert request_hook < register_call
    assert third_party.index("EventType.OnLLMRequestEvent") < third_party.index("runner = DifyAgentRunner")
    assert "async def on_agent_done" in hooks
    assert hooks.count("EventType.OnLLMResponseEvent") == 1
    assert hooks.index("EventType.OnLLMResponseEvent") < hooks.index("EventType.OnAgentDoneEvent")
    assert "async def on_tool_start" in hooks and "async def on_tool_end" in hooks
    assert decorate.index("EventType.OnDecoratingResultEvent") < decorate.index("if is_stream:\n            return")

    streaming_send = respond.index("await event.send_streaming")
    after_sent = respond.index("EventType.OnAfterMessageSentEvent")
    assert streaming_send < respond.index("return", streaming_send) < after_sent
    assert respond.count("except Exception as e:") >= 3
    assert respond.rindex("logger.error", 0, after_sent) < after_sent


@pytest.mark.parametrize(
    ("case", "expected"),
    [
        ("ordinary", ActualAction.UNKNOWN),
        ("silent", ActualAction.HOLD),
        ("fallback", ActualAction.UNKNOWN),
        ("tool_loop", ActualAction.UNKNOWN),
        ("repeated_provider_response", ActualAction.UNMATCHED_RESPONSE),
        ("streaming", ActualAction.UNKNOWN),
        ("media", ActualAction.UNKNOWN),
        ("provider_exception", ActualAction.UNKNOWN),
        ("unaddressed_group", ActualAction.UNMATCHED_RESPONSE),
        ("partial_send", ActualAction.UNKNOWN),
        ("cancelled_segmented_send", ActualAction.UNKNOWN),
        ("segmented_success", ActualAction.SPEAK),
        ("proactive_dispatched", ActualAction.REACH),
    ],
)
def test_hook_matrix_uses_only_structured_terminal_evidence(
    case: str,
    expected: ActualAction,
) -> None:
    result = _run_hook_case(case)
    assert result.actual_action is expected
    assert result.captures in (0, 1)
    assert result.accepted_terminal_claims <= result.captures
    assert result.accepted_terminal_claims <= 1
    assert result.projected_call_count == result.accepted_terminal_claims
    if case == "unaddressed_group":
        assert (
            result.captures,
            result.terminal_attempts,
            result.accepted_terminal_claims,
            result.projected_call_count,
        ) == (0, 1, 0, 0)
    elif case == "repeated_provider_response":
        assert (
            result.captures,
            result.terminal_attempts,
            result.accepted_terminal_claims,
            result.projected_call_count,
        ) == (1, 2, 1, 1)
    else:
        assert (
            result.captures,
            result.terminal_attempts,
            result.accepted_terminal_claims,
            result.projected_call_count,
        ) == (1, 1, 1, 1)


def test_after_message_sent_is_attempt_evidence_not_send_success() -> None:
    respond = _source("core/pipeline/respond/stage.py")
    after_sent = respond.index("EventType.OnAfterMessageSentEvent")
    send_try = respond.index("try:\n                        await event.send", respond.index("if len(result.chain) > 0"))
    swallowed_failure = respond.index("except Exception as e:", send_try)
    assert send_try < swallowed_failure < after_sent

    ordinary = _ordinary_candidate()
    assert ordinary.after_message_sent is True
    assert project_actual_action(ordinary) is ActualAction.UNKNOWN


def test_real_plugin_lock_delegates_to_session_context_production_lock() -> None:
    root = Path(__file__).resolve().parents[2]
    main_source = (root / "main.py").read_text(encoding="utf-8")
    context_source = (root / "sylanne_alpha/session_context.py").read_text(encoding="utf-8")
    assert "return self._session_ctx.session_lock(session_key)" in main_source
    assert "locks = self._p._store.session_locks" in context_source
    assert "return locks.get(session_key)" in context_source
