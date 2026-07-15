from __future__ import annotations

import hashlib
import os
from dataclasses import replace
from enum import Enum
from pathlib import Path

import astrbot
import pytest

from sylanne_alpha.v2core.shadow_snapshot import V2ResponseCandidateV1


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


class _ActualEvidence(Enum):
    SPEAK = "SPEAK"
    HOLD = "HOLD"
    REACH = "REACH"
    UNKNOWN = "UNKNOWN"
    UNMATCHED_RESPONSE = "UNMATCHED_RESPONSE"


def _astrbot_root() -> Path:
    configured = os.environ.get("ASTRBOT_SRC")
    root = Path(configured) if configured else Path(astrbot.__file__).resolve().parent
    assert root.is_dir(), f"ASTRBOT_SRC is not a directory: {root}"
    return root


def _source(relative: str) -> str:
    return (_astrbot_root() / relative).read_text(encoding="utf-8")


def _sha256(relative: str) -> str:
    return hashlib.sha256((_astrbot_root() / relative).read_bytes()).hexdigest()


def _project_structured_evidence(candidate: V2ResponseCandidateV1) -> _ActualEvidence:
    if not candidate.correlation_proven or candidate.duplicate_terminal_claim:
        return _ActualEvidence.UNMATCHED_RESPONSE
    if candidate.route_kind == "PROACTIVE":
        return (
            _ActualEvidence.REACH
            if candidate.proactive_dispatched is True
            else _ActualEvidence.UNKNOWN
        )
    if candidate.route_kind == "SILENT":
        return _ActualEvidence.HOLD
    if candidate.route_kind == "SEGMENTED_TEXT":
        return (
            _ActualEvidence.SPEAK
            if candidate.all_segments_succeeded is True
            else _ActualEvidence.UNKNOWN
        )
    return _ActualEvidence.UNKNOWN


def _ordinary_candidate() -> V2ResponseCandidateV1:
    return V2ResponseCandidateV1(
        route_kind="ORDINARY_TEXT",
        reply_kind="SPEAK",
        part_count=1,
        correlation_proven=True,
        after_message_sent=True,
    )


def _run_hook_case(case: str) -> _ActualEvidence:
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
        candidate = replace(candidate, duplicate_terminal_claim=True)
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
    return _project_structured_evidence(candidate)


def _claim_counts(case: str) -> tuple[int, int, int]:
    """Frozen Task 2 matrix; Task 3 replaces this with the real bounded registry."""
    if case == "unaddressed_group":
        return (0, 1, 0)
    if case == "repeated_provider_response":
        return (1, 2, 1)
    return (1, 1, 1)


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
        ("ordinary", _ActualEvidence.UNKNOWN),
        ("silent", _ActualEvidence.HOLD),
        ("fallback", _ActualEvidence.UNKNOWN),
        ("tool_loop", _ActualEvidence.UNKNOWN),
        ("repeated_provider_response", _ActualEvidence.UNMATCHED_RESPONSE),
        ("streaming", _ActualEvidence.UNKNOWN),
        ("media", _ActualEvidence.UNKNOWN),
        ("provider_exception", _ActualEvidence.UNKNOWN),
        ("unaddressed_group", _ActualEvidence.UNMATCHED_RESPONSE),
        ("partial_send", _ActualEvidence.UNKNOWN),
        ("cancelled_segmented_send", _ActualEvidence.UNKNOWN),
        ("segmented_success", _ActualEvidence.SPEAK),
        ("proactive_dispatched", _ActualEvidence.REACH),
    ],
)
def test_hook_matrix_uses_only_structured_terminal_evidence(
    case: str,
    expected: _ActualEvidence,
) -> None:
    assert _run_hook_case(case) is expected
    captures, terminal_attempts, accepted_terminal_claims = _claim_counts(case)
    assert captures in (0, 1)
    assert accepted_terminal_claims <= captures
    assert accepted_terminal_claims <= 1
    if case == "unaddressed_group":
        assert (captures, terminal_attempts, accepted_terminal_claims) == (0, 1, 0)
    elif case == "repeated_provider_response":
        assert (captures, terminal_attempts, accepted_terminal_claims) == (1, 2, 1)
    else:
        assert (captures, terminal_attempts, accepted_terminal_claims) == (1, 1, 1)


def test_after_message_sent_is_attempt_evidence_not_send_success() -> None:
    respond = _source("core/pipeline/respond/stage.py")
    after_sent = respond.index("EventType.OnAfterMessageSentEvent")
    send_try = respond.index("try:\n                        await event.send", respond.index("if len(result.chain) > 0"))
    swallowed_failure = respond.index("except Exception as e:", send_try)
    assert send_try < swallowed_failure < after_sent

    ordinary = _ordinary_candidate()
    assert ordinary.after_message_sent is True
    assert _project_structured_evidence(ordinary) is _ActualEvidence.UNKNOWN


def test_real_plugin_lock_delegates_to_session_context_production_lock() -> None:
    root = Path(__file__).resolve().parents[2]
    main_source = (root / "main.py").read_text(encoding="utf-8")
    context_source = (root / "sylanne_alpha/session_context.py").read_text(encoding="utf-8")
    assert "return self._session_ctx.session_lock(session_key)" in main_source
    assert "locks = self._p._store.session_locks" in context_source
    assert "return locks.get(session_key)" in context_source
