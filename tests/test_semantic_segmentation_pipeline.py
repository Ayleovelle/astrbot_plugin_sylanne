"""Pipeline integration tests for nonce-scoped semantic beat scrubbing."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from sylanne_alpha.llm_response_pipeline import LLMResponsePipeline
from sylanne_alpha.message_dispatch import strip_draft_blocks
from sylanne_alpha.semantic_segmentation import (
    PauseClass,
    SEMANTIC_BEAT_NONCE_EXTRA,
    build_marker,
)


class _Event:
    def __init__(self, nonce: str | None = None) -> None:
        self.extras: dict[str, object] = {}
        if nonce is not None:
            self.extras[SEMANTIC_BEAT_NONCE_EXTRA] = nonce

    def get_extra(self, key: str, default=None):
        return self.extras.get(key, default)

    def set_extra(self, key: str, value: object) -> None:
        self.extras[key] = value


def _pipeline() -> LLMResponsePipeline:
    return LLMResponsePipeline(SimpleNamespace())


def test_response_parse_returns_clean_model_plan_and_bounded_correlation() -> None:
    pipeline = _pipeline()
    event = _Event("A1B2C3")
    marker = build_marker("A1B2C3", PauseClass.DEEP)
    raw = f"第一段{marker}第二段"

    cleaned, parts = pipeline._parse_semantic_response(
        event,
        original_text=raw,
        sanitized_text=raw,
    )

    assert cleaned == "第一段第二段"
    assert parts is not None
    assert [(part.text, part.pause_before) for part in parts] == [
        ("第一段", None),
        ("第二段", PauseClass.DEEP),
    ]
    correlation = event.extras[pipeline._SEMANTIC_CORRELATION_EXTRA]
    assert isinstance(correlation, dict)
    assert set(correlation) == {
        "nonce",
        "raw_chars",
        "raw_sha256",
        "clean_chars",
        "clean_sha256",
    }
    assert raw not in repr(correlation)


def test_on_agent_done_replaces_only_exact_final_raw_assistant_entry() -> None:
    pipeline = _pipeline()
    event = _Event("A1B2C3")
    marker = build_marker("A1B2C3", PauseClass.NORMAL)
    raw = f"<thinking>secret</thinking>第一{marker}第二[sylanne_fake]"
    sanitized = pipeline._sanitize_response(strip_draft_blocks(raw))
    cleaned, _ = pipeline._parse_semantic_response(
        event,
        original_text=raw,
        sanitized_text=sanitized,
    )
    text_part = SimpleNamespace(text=raw)
    run_context = SimpleNamespace(
        messages=[SimpleNamespace(role="user", content="hi"), SimpleNamespace(role="assistant", content=[text_part])]
    )
    response = SimpleNamespace(completion_text=raw)

    assert pipeline.on_agent_done(event, run_context, response) is True
    assert text_part.text == cleaned == "第一第二"
    assert response.completion_text == "第一第二"


def test_on_agent_done_refuses_hash_mismatch() -> None:
    pipeline = _pipeline()
    event = _Event("A1B2C3")
    marker = build_marker("A1B2C3", PauseClass.SOFT)
    raw = f"一{marker}二"
    pipeline._parse_semantic_response(event, original_text=raw, sanitized_text=raw)
    text_part = SimpleNamespace(text=raw + "被改过")
    run_context = SimpleNamespace(
        messages=[SimpleNamespace(role="assistant", content=[text_part])]
    )

    assert pipeline.on_agent_done(event, run_context, SimpleNamespace()) is False
    assert text_part.text == raw + "被改过"


def test_on_agent_done_scrubs_real_astrbot_message_shape() -> None:
    message_module = pytest.importorskip("astrbot.core.agent.message")
    pipeline = _pipeline()
    event = _Event("A1B2C3")
    marker = build_marker("A1B2C3", PauseClass.DEEP)
    raw = f"前{marker}后"
    cleaned, _ = pipeline._parse_semantic_response(
        event,
        original_text=raw,
        sanitized_text=raw,
    )
    message = message_module.Message(
        role="assistant",
        content=[message_module.TextPart(text=raw)],
    )
    run_context = SimpleNamespace(messages=[message])

    assert pipeline.on_agent_done(event, run_context, SimpleNamespace()) is True
    assert message.content[0].text == cleaned == "前后"


def test_final_guard_scrubs_owned_malformed_and_foreign_nonce_markers() -> None:
    pipeline = _pipeline()
    event = _Event("A1B2C3")
    owned = '<syl-beat nonce="A1B2C3" pause="unknown"/>'
    foreign = '<syl-beat nonce="FFFFFF" pause="deep"/>'

    assert pipeline.scrub_owned_semantic_markers(event, f"前{owned}后") == "前后"
    assert pipeline.scrub_owned_semantic_markers(event, f"前{foreign}后") == "前后"


def test_final_guard_scrubs_marker_even_when_turn_nonce_is_missing() -> None:
    pipeline = _pipeline()
    event = _Event()

    assert (
        pipeline.scrub_owned_semantic_markers(
            event,
            '前<syl-beat pause="soft"/>后',
        )
        == "前后"
    )


def test_main_registers_history_scrub_and_final_plain_leak_guard() -> None:
    source = (Path(__file__).resolve().parents[1] / "main.py").read_text(encoding="utf-8")

    assert "def _optional_agent_done_filter" in source
    assert "@_optional_agent_done_filter(priority=1000)" in source
    assert "self._llm_response_pipeline.on_agent_done(event, run_context, response)" in source
    assert "self._llm_response_pipeline.scrub_owned_semantic_markers(" in source
