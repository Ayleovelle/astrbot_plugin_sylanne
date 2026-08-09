"""Contract tests for model-authored semantic beat markers."""

from __future__ import annotations

import pytest

from sylanne_alpha.semantic_segmentation import (
    MAX_SEMANTIC_COMPLETION_CHARS,
    PauseClass,
    SemanticBeatPart,
    build_marker,
    parse_semantic_completion,
)


NONCE = "A7K3Q2"


def test_build_marker_uses_the_exact_control_grammar() -> None:
    assert build_marker(NONCE, PauseClass.SOFT) == ('<syl-beat nonce="A7K3Q2" pause="soft"/>')


def test_parser_preserves_visible_text_exactly() -> None:
    raw = "愿望啊……\n" + build_marker(NONCE, PauseClass.NORMAL) + "其实愿望很多。"

    plan = parse_semantic_completion(raw, nonce=NONCE)

    assert plan.accepted is True
    assert plan.clean_text == "愿望啊……\n其实愿望很多。"
    assert "".join(part.text for part in plan.parts) == plan.clean_text
    assert [part.pause_before for part in plan.parts] == [None, PauseClass.NORMAL]
    assert plan.rejection_reason is None


def test_wrong_nonce_is_not_interpreted_but_is_scrubbed_from_visible_text() -> None:
    raw = '原文<syl-beat nonce="OTHER1" pause="deep"/>保留'

    plan = parse_semantic_completion(raw, nonce=NONCE)

    assert plan.accepted is False
    assert plan.clean_text == "原文保留"
    assert plan.parts == ()
    assert plan.rejection_reason == "UNSCOPED_MARKER"


@pytest.mark.parametrize(
    "marker",
    [
        '<syl-beat pause="soft"/>',
        '<syl-beat nonce="A7K3Q3" pause="soft"/>',
        '<SYL-BEAT nonce="A7K3Q2" pause="soft"/>',
        '</syl-beat>',
    ],
)
def test_every_raw_semantic_marker_candidate_is_scrubbed(marker: str) -> None:
    plan = parse_semantic_completion(f"前{marker}后", nonce=NONCE)

    assert plan.accepted is False
    assert plan.clean_text == "前后"
    assert plan.parts == ()
    assert plan.rejection_reason == "UNSCOPED_MARKER"


def test_marker_like_user_text_is_left_untouched() -> None:
    raw = '用户写了 &lt;syl-beat nonce="A7K3Q2" pause="soft"/&gt;，并没有输出控制标记。'

    plan = parse_semantic_completion(raw, nonce=NONCE)

    assert plan.accepted is True
    assert plan.clean_text == raw
    assert plan.parts == (SemanticBeatPart(text=raw, pause_before=None),)


def test_malformed_owned_marker_falls_back_clean_without_leak() -> None:
    raw = '前半<syl-beat nonce="A7K3Q2" pause="unknown"/>后半'

    plan = parse_semantic_completion(raw, nonce=NONCE)

    assert plan.accepted is False
    assert plan.clean_text == "前半后半"
    assert plan.parts == ()
    assert plan.rejection_reason == "UNKNOWN_PAUSE"


@pytest.mark.parametrize("pause", list(PauseClass))
def test_parser_accepts_every_pause_class(pause: PauseClass) -> None:
    marker = build_marker(NONCE, pause)

    plan = parse_semantic_completion(f"前{marker}后", nonce=NONCE)

    assert plan.accepted is True
    assert plan.parts == (
        SemanticBeatPart(text="前", pause_before=None),
        SemanticBeatPart(text="后", pause_before=pause),
    )


def test_crlf_newlines_and_spaces_are_conserved_byte_for_byte() -> None:
    marker = build_marker(NONCE, PauseClass.DEEP)
    raw = f"第一行\r\n  第二行\r\n{marker}\r\n第三行  "

    plan = parse_semantic_completion(raw, nonce=NONCE)

    assert plan.accepted is True
    assert plan.clean_text == "第一行\r\n  第二行\r\n\r\n第三行  "
    assert plan.parts[0].text == "第一行\r\n  第二行\r\n"
    assert plan.parts[1].text == "\r\n第三行  "
    assert "".join(part.text for part in plan.parts) == plan.clean_text


def test_zero_markers_uses_model_authored_line_breaks_as_beats() -> None:
    raw = "第一句。\n第二句！\n\n第三段？"

    plan = parse_semantic_completion(raw, nonce=NONCE)

    assert plan.accepted is True
    assert plan.clean_text == raw
    assert plan.parts == (
        SemanticBeatPart(text="第一句。\n", pause_before=None),
        SemanticBeatPart(text="第二句！\n\n", pause_before=PauseClass.SOFT),
        SemanticBeatPart(text="第三段？", pause_before=PauseClass.NORMAL),
    )
    assert "".join(part.text for part in plan.parts) == raw


@pytest.mark.parametrize(
    "raw",
    [
        "```python\nprint('a')\nprint('b')\n```",
        "| name | value |\n| --- | --- |\n| a | 1 |",
        "- 第一项\n- 第二项\n- 第三项",
    ],
)
def test_zero_marker_structured_content_is_not_split_per_line(raw: str) -> None:
    plan = parse_semantic_completion(raw, nonce=NONCE)

    assert plan.accepted is True
    assert plan.clean_text == raw
    assert plan.parts == (SemanticBeatPart(text=raw, pause_before=None),)


def test_five_markers_create_the_maximum_six_nonempty_parts() -> None:
    markers = [
        build_marker(NONCE, PauseClass.SOFT),
        build_marker(NONCE, PauseClass.NORMAL),
        build_marker(NONCE, PauseClass.DEEP),
        build_marker(NONCE, PauseClass.SOFT),
        build_marker(NONCE, PauseClass.NORMAL),
    ]
    raw = "甲" + "乙".join(markers) + "丙"

    plan = parse_semantic_completion(raw, nonce=NONCE)

    assert plan.accepted is True
    assert len(plan.parts) == 6
    assert [part.pause_before for part in plan.parts] == [
        None,
        PauseClass.SOFT,
        PauseClass.NORMAL,
        PauseClass.DEEP,
        PauseClass.SOFT,
        PauseClass.NORMAL,
    ]
    assert "".join(part.text for part in plan.parts) == plan.clean_text


def test_punctuation_only_model_beat_is_folded_without_losing_boundaries() -> None:
    raw = (
        "嗯……"
        + build_marker(NONCE, PauseClass.NORMAL)
        + "……"
        + build_marker(NONCE, PauseClass.DEEP)
        + "你说这种话的时候能不能提前通知一下\n\n我没有防备的😾"
        + build_marker(NONCE, PauseClass.NORMAL)
        + "但是不许用这个当借口熬夜啊\n\n身体搞坏了我打你"
    )

    plan = parse_semantic_completion(raw, nonce=NONCE)

    assert plan.accepted is True
    assert plan.parts == (
        SemanticBeatPart(text="嗯…………", pause_before=None),
        SemanticBeatPart(
            text="你说这种话的时候能不能提前通知一下\n\n",
            pause_before=PauseClass.DEEP,
        ),
        SemanticBeatPart(text="我没有防备的😾", pause_before=PauseClass.NORMAL),
        SemanticBeatPart(
            text="但是不许用这个当借口熬夜啊\n\n",
            pause_before=PauseClass.NORMAL,
        ),
        SemanticBeatPart(text="身体搞坏了我打你", pause_before=PauseClass.NORMAL),
    )
    assert plan.rejection_reason is None
    assert plan.clean_text == (
        "嗯…………你说这种话的时候能不能提前通知一下\n\n我没有防备的😾"
        "但是不许用这个当借口熬夜啊\n\n身体搞坏了我打你"
    )


def test_folded_punctuation_beat_preserves_the_stronger_pause() -> None:
    raw = (
        "前"
        + build_marker(NONCE, PauseClass.DEEP)
        + "……"
        + build_marker(NONCE, PauseClass.SOFT)
        + "后"
    )

    plan = parse_semantic_completion(raw, nonce=NONCE)

    assert plan.accepted is True
    assert plan.parts == (
        SemanticBeatPart(text="前……", pause_before=None),
        SemanticBeatPart(text="后", pause_before=PauseClass.DEEP),
    )


def test_six_markers_are_rejected_and_all_owned_markers_are_scrubbed() -> None:
    marker = build_marker(NONCE, PauseClass.SOFT)
    raw = marker.join("甲乙丙丁戊己庚")

    plan = parse_semantic_completion(raw, nonce=NONCE)

    assert plan.accepted is False
    assert plan.clean_text == "甲乙丙丁戊己庚"
    assert plan.parts == ()
    assert plan.rejection_reason == "TOO_MANY_MARKERS"
    assert "<syl-beat" not in plan.clean_text


@pytest.mark.parametrize(
    "raw",
    [
        f"前{build_marker(NONCE, PauseClass.SOFT)}{build_marker(NONCE, PauseClass.DEEP)}后",
        f"前{build_marker(NONCE, PauseClass.SOFT)} \r\n\t{build_marker(NONCE, PauseClass.NORMAL)}后",
        f"{build_marker(NONCE, PauseClass.NORMAL)}只有后半",
        f"只有前半{build_marker(NONCE, PauseClass.NORMAL)}",
    ],
)
def test_empty_or_whitespace_only_visible_parts_are_rejected(raw: str) -> None:
    plan = parse_semantic_completion(raw, nonce=NONCE)

    assert plan.accepted is False
    assert plan.parts == ()
    assert plan.rejection_reason == "EMPTY_PART"
    assert "<syl-beat" not in plan.clean_text


def test_whitespace_only_completion_is_rejected() -> None:
    plan = parse_semantic_completion(" \r\n\t", nonce=NONCE)

    assert plan.accepted is False
    assert plan.clean_text == " \r\n\t"
    assert plan.parts == ()
    assert plan.rejection_reason == "EMPTY_PART"


@pytest.mark.parametrize(
    ("raw", "expected_reason"),
    [
        ('前<syl-beat pause="soft" nonce="A7K3Q2"/>后', "MALFORMED_MARKER"),
        ('前<syl-beat nonce="A7K3Q2" pause="soft">后', "MALFORMED_MARKER"),
        ('前<syl-beat nonce="A7K3Q2"/>后', "MALFORMED_MARKER"),
        (
            '前<syl-beat nonce="A7K3Q2" pause="soft" extra="x"/>后',
            "MALFORMED_MARKER",
        ),
        ("前<syl-beat nonce='A7K3Q2' pause='soft'/>后", "MALFORMED_MARKER"),
        ('前<syl-beat nonce=A7K3Q2 pause="soft"/>后', "MALFORMED_MARKER"),
    ],
)
def test_malformed_owned_xml_is_rejected_and_scrubbed(
    raw: str,
    expected_reason: str,
) -> None:
    plan = parse_semantic_completion(raw, nonce=NONCE)

    assert plan.accepted is False
    assert plan.clean_text == "前后"
    assert plan.parts == ()
    assert plan.rejection_reason == expected_reason
    assert "syl-beat" not in plan.clean_text


def test_multiline_owned_marker_is_rejected_and_fully_scrubbed() -> None:
    raw = '前<syl-beat\n nonce="A7K3Q2"\n pause="soft"/>后'

    plan = parse_semantic_completion(raw, nonce=NONCE)

    assert plan.accepted is False
    assert plan.clean_text == "前后"
    assert plan.parts == ()
    assert plan.rejection_reason == "MALFORMED_MARKER"


def test_unclosed_marker_never_consumes_following_visible_text() -> None:
    raw = '前<syl-beat nonce="A7K3Q2" pause="soft" 后正文仍应保留'

    plan = parse_semantic_completion(raw, nonce=NONCE)

    assert plan.accepted is False
    assert plan.rejection_reason == "UNSCOPED_MARKER"
    assert "<syl-beat" not in plan.clean_text
    assert plan.clean_text == "前后正文仍应保留"
    assert "nonce=" not in plan.clean_text
    assert "pause=" not in plan.clean_text


@pytest.mark.parametrize(
    "raw",
    [
        "```text\n前" + build_marker(NONCE, PauseClass.SOFT) + "后\n```",
        "正文 `前" + build_marker(NONCE, PauseClass.NORMAL) + "后` 结尾",
        "https://example.test/a" + build_marker(NONCE, PauseClass.DEEP) + "/b",
        "| 左 | 前" + build_marker(NONCE, PauseClass.SOFT) + "后 | 右 |",
    ],
)
def test_owned_marker_in_protected_markdown_region_is_rejected(raw: str) -> None:
    plan = parse_semantic_completion(raw, nonce=NONCE)

    assert plan.accepted is False
    assert plan.parts == ()
    assert plan.rejection_reason == "MARKER_IN_PROTECTED_REGION"
    assert "<syl-beat" not in plan.clean_text


def test_exact_input_bound_is_accepted() -> None:
    marker = build_marker(NONCE, PauseClass.NORMAL)
    suffix_length = MAX_SEMANTIC_COMPLETION_CHARS - 5_000 - len(marker)
    raw = "甲" * 5_000 + marker + "乙" * suffix_length
    assert len(raw) == MAX_SEMANTIC_COMPLETION_CHARS

    plan = parse_semantic_completion(raw, nonce=NONCE)

    assert plan.accepted is True
    assert len(plan.parts) == 2
    assert "".join(part.text for part in plan.parts) == plan.clean_text


def test_input_over_bound_is_rejected_after_scrubbing_owned_markers() -> None:
    marker = build_marker(NONCE, PauseClass.NORMAL)
    suffix_length = MAX_SEMANTIC_COMPLETION_CHARS + 1 - 5_000 - len(marker)
    raw = "甲" * 5_000 + marker + "乙" * suffix_length
    assert len(raw) == MAX_SEMANTIC_COMPLETION_CHARS + 1

    plan = parse_semantic_completion(raw, nonce=NONCE)

    assert plan.accepted is False
    assert plan.parts == ()
    assert plan.rejection_reason == "INPUT_TOO_LONG"
    assert plan.clean_text == "甲" * 5_000 + "乙" * suffix_length
    assert "<syl-beat" not in plan.clean_text
