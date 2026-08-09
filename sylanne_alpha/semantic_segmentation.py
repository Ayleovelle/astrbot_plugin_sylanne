"""Parse model-authored semantic beats from markers or visible line breaks."""

from __future__ import annotations

import re
import secrets
import unicodedata
from dataclasses import dataclass
from enum import Enum


MAX_SEMANTIC_COMPLETION_CHARS = 10_000
MAX_SEMANTIC_MARKERS = 5
SEMANTIC_BEAT_NONCE_EXTRA = "_syl_semantic_beat_nonce"
_ANY_MARKER_PATTERN = re.compile(
    # Only consume syntactic attributes after the tag name.  This removes the
    # hidden nonce/pause residue from an unclosed marker without treating all
    # following prose up to some later ``>`` as control text.
    r"""
    </?syl-beat\b
    (?:
        \s+[A-Za-z_:][\w:.-]*\s*=\s*
        (?:"[^"]*"|'[^']*'|[^\s<>]+)
    )*
    \s*/?>?
    """,
    re.IGNORECASE | re.VERBOSE,
)
_LINE_BREAK_PATTERN = re.compile(r"(?:\r\n|\n|\r)(?:[ \t]*(?:\r\n|\n|\r))*")
_LIST_LINE_PATTERN = re.compile(r"^[ \t]{0,3}(?:[-+*]\s+|\d+[.)]\s+|>\s+)")


class PauseClass(str, Enum):
    """A model-authored pause before the following visible part."""

    SOFT = "soft"
    NORMAL = "normal"
    DEEP = "deep"


@dataclass(frozen=True, slots=True)
class SemanticBeatPart:
    """One exact visible-text slice and the pause that precedes it."""

    text: str
    pause_before: PauseClass | None


@dataclass(frozen=True, slots=True)
class SemanticBeatPlan:
    """The validated delivery plan or a scrubbed fail-closed result."""

    clean_text: str
    parts: tuple[SemanticBeatPart, ...]
    accepted: bool
    rejection_reason: str | None = None


def build_marker(nonce: str, pause: PauseClass) -> str:
    """Return the only marker grammar accepted for ``nonce`` and ``pause``."""

    return f'<syl-beat nonce="{nonce}" pause="{pause.value}"/>'


def new_semantic_nonce() -> str:
    """Return a compact, unpredictable nonce scoped to one response turn."""

    return secrets.token_hex(3).upper()


def semantic_beat_system_contract(nonce: str) -> str:
    """Build the bounded same-call contract for model-authored beat markers."""

    markers = "、".join(build_marker(nonce, pause) for pause in PauseClass)
    return (
        "[即时聊天语义节拍]\n"
        f"可在自然语义边界插入 0 到 5 个隐藏标记：{markers}。"
        "标记只控制发送节拍；先正常写好回复，不要改写正文，不要解释或引用标记，"
        "宁可少分几个完整节拍，也不要切成许多短气泡；"
        "不要把单独的省略号或其他纯标点切成一个节拍；"
        "deep 只用于揭示、转折、犹豫或情绪落点；"
        "不要把标记放进代码、URL、表格或其他结构化内容。"
    )


def _owned_marker_pattern(nonce: str) -> re.Pattern[str]:
    """Build a bounded candidate matcher scoped to one escaped nonce."""

    escaped_nonce = re.escape(nonce)
    nonce_value = (
        rf'(?:"{escaped_nonce}"|\'{escaped_nonce}\'|{escaped_nonce})'
        r"(?=[\s/>])"
    )
    return re.compile(
        r"<syl-beat\b"
        rf"(?=[^<>]*\bnonce\s*=\s*{nonce_value})"
        r"[^<>]*/?>"
    )


def _pause_attribute_value(marker: str) -> str | None:
    match = re.search(
        r"\bpause\s*=\s*(?:\"(?P<double>[^\"]*)\"|"
        r"'(?P<single>[^']*)'|(?P<bare>[^\s/>]+))",
        marker,
    )
    if match is None:
        return None
    return next(
        (value for value in match.group("double", "single", "bare") if value is not None),
        None,
    )


def _remove_matches(text: str, matches: tuple[re.Match[str], ...]) -> str:
    if not matches:
        return text
    chunks: list[str] = []
    cursor = 0
    for match in matches:
        chunks.append(text[cursor : match.start()])
        cursor = match.end()
    chunks.append(text[cursor:])
    return "".join(chunks)


def scrub_semantic_marker_candidates(text: str) -> str:
    """Remove every raw ``syl-beat`` control candidate from visible text.

    Only exact current-nonce markers may influence segmentation, but malformed,
    missing-nonce, wrong-nonce, and closing-tag variants are still plugin
    control residue and must never reach chat output or persisted history.
    HTML-escaped examples are ordinary visible text and remain untouched.
    """

    return _remove_matches(text, tuple(_ANY_MARKER_PATTERN.finditer(text)))


def _line_ranges(text: str) -> tuple[tuple[int, int, str], ...]:
    lines: list[tuple[int, int, str]] = []
    offset = 0
    for line in text.splitlines(keepends=True):
        end = offset + len(line)
        lines.append((offset, end, line))
        offset = end
    if offset < len(text):
        lines.append((offset, len(text), text[offset:]))
    return tuple(lines)


def _fenced_code_ranges(text: str) -> tuple[tuple[int, int], ...]:
    ranges: list[tuple[int, int]] = []
    fence_start: int | None = None
    fence_char = ""
    fence_length = 0

    for start, end, line in _line_ranges(text):
        stripped = line.lstrip(" \t")
        indent = len(line) - len(stripped)
        opener = re.match(r"(`{3,}|~{3,})", stripped) if indent <= 3 else None
        if fence_start is None:
            if opener is not None:
                token = opener.group(1)
                fence_start = start
                fence_char = token[0]
                fence_length = len(token)
            continue
        if opener is None:
            continue
        token = opener.group(1)
        if token[0] == fence_char and len(token) >= fence_length:
            ranges.append((fence_start, end))
            fence_start = None
            fence_char = ""
            fence_length = 0

    if fence_start is not None:
        ranges.append((fence_start, len(text)))
    return tuple(ranges)


def _inline_code_ranges(text: str) -> tuple[tuple[int, int], ...]:
    ranges: list[tuple[int, int]] = []
    cursor = 0
    while cursor < len(text):
        if text[cursor] != "`":
            cursor += 1
            continue
        run_end = cursor + 1
        while run_end < len(text) and text[run_end] == "`":
            run_end += 1
        delimiter = text[cursor:run_end]
        line_end = text.find("\n", run_end)
        if line_end < 0:
            line_end = len(text)
        close = text.find(delimiter, run_end, line_end)
        if close < 0:
            ranges.append((cursor, line_end))
            cursor = line_end
            continue
        end = close + len(delimiter)
        ranges.append((cursor, end))
        cursor = end
    return tuple(ranges)


def _protected_ranges(text: str) -> tuple[tuple[int, int], ...]:
    ranges = list(_fenced_code_ranges(text))
    ranges.extend(_inline_code_ranges(text))
    ranges.extend(match.span() for match in re.finditer(r"(?i)\b(?:https?://|www\.)\S+", text))
    ranges.extend((start, end) for start, end, line in _line_ranges(text) if line.count("|") >= 2)
    return tuple(ranges)


def _has_multiline_structure(text: str) -> bool:
    """Keep code, tables, and list blocks intact instead of making one bubble per row."""

    if _fenced_code_ranges(text):
        return True
    lines = [line.rstrip("\r\n") for _, _, line in _line_ranges(text)]
    if any(line.count("|") >= 2 for line in lines):
        return True
    if sum(1 for line in lines if _LIST_LINE_PATTERN.match(line)) >= 2:
        return True
    return sum(1 for line in lines if line.startswith(("    ", "\t"))) >= 2


def _overlaps(left: tuple[int, int], right: tuple[int, int]) -> bool:
    return left[0] < right[1] and right[0] < left[1]


def _rejected(clean_text: str, reason: str) -> SemanticBeatPlan:
    return SemanticBeatPlan(
        clean_text=clean_text,
        parts=(),
        accepted=False,
        rejection_reason=reason,
    )


def _has_substantive_content(text: str) -> bool:
    """Return whether a beat contains more than whitespace/control punctuation."""

    return any(
        not char.isspace()
        and unicodedata.category(char)[0] not in {"C", "P", "Z"}
        for char in text
    )


_PAUSE_STRENGTH = {
    None: -1,
    PauseClass.SOFT: 0,
    PauseClass.NORMAL: 1,
    PauseClass.DEEP: 2,
}


def _stronger_pause(
    left: PauseClass | None,
    right: PauseClass | None,
) -> PauseClass | None:
    return left if _PAUSE_STRENGTH[left] >= _PAUSE_STRENGTH[right] else right


def _fold_punctuation_only_parts(
    parts: list[SemanticBeatPart],
    *,
    clean_text: str,
) -> tuple[SemanticBeatPart, ...]:
    """Keep authored boundaries while preventing punctuation-only chat bubbles."""

    folded: list[SemanticBeatPart] = []
    leading_text: list[str] = []
    pending_pause: PauseClass | None = None

    for part in parts:
        if _has_substantive_content(part.text):
            if not folded:
                folded.append(
                    SemanticBeatPart(
                        text="".join(leading_text) + part.text,
                        pause_before=None,
                    )
                )
            else:
                folded.append(
                    SemanticBeatPart(
                        text=part.text,
                        pause_before=_stronger_pause(
                            pending_pause,
                            part.pause_before,
                        ),
                    )
                )
            leading_text.clear()
            pending_pause = None
            continue

        if folded:
            previous = folded[-1]
            folded[-1] = SemanticBeatPart(
                text=previous.text + part.text,
                pause_before=previous.pause_before,
            )
        else:
            leading_text.append(part.text)
        pending_pause = _stronger_pause(pending_pause, part.pause_before)

    if not folded:
        return (SemanticBeatPart(text=clean_text, pause_before=None),)
    return tuple(folded)


def _parts_from_authored_line_breaks(
    text: str,
    *,
    minimum_line_breaks: int = 1,
) -> tuple[SemanticBeatPart, ...]:
    """Use visible line breaks as bounded beats without guessing sentence boundaries."""

    if _has_multiline_structure(text):
        return (SemanticBeatPart(text=text, pause_before=None),)

    boundaries: list[re.Match[str]] = []
    for match in _LINE_BREAK_PATTERN.finditer(text):
        line_break_count = len(re.findall(r"\r\n|\n|\r", match.group(0)))
        if (
            line_break_count >= max(1, minimum_line_breaks)
            and text[: match.start()].strip()
            and text[match.end() :].strip()
        ):
            boundaries.append(match)
            if len(boundaries) >= MAX_SEMANTIC_MARKERS:
                break
    if not boundaries:
        return (SemanticBeatPart(text=text, pause_before=None),)

    parts: list[SemanticBeatPart] = []
    cursor = 0
    pause_before: PauseClass | None = None
    for boundary in boundaries:
        parts.append(
            SemanticBeatPart(
                text=text[cursor : boundary.end()],
                pause_before=pause_before,
            )
        )
        line_break_count = len(re.findall(r"\r\n|\n|\r", boundary.group(0)))
        pause_before = (
            PauseClass.NORMAL if line_break_count >= 2 else PauseClass.SOFT
        )
        cursor = boundary.end()
    parts.append(SemanticBeatPart(text=text[cursor:], pause_before=pause_before))
    return _fold_punctuation_only_parts(parts, clean_text=text)


def semantic_parts_from_visible_line_breaks(
    text: str,
) -> tuple[SemanticBeatPart, ...]:
    """Return safe model-authored beats after all control markers are gone."""

    return _parts_from_authored_line_breaks(text)


def _refine_parts_with_authored_line_breaks(
    parts: tuple[SemanticBeatPart, ...],
) -> tuple[SemanticBeatPart, ...]:
    """Honor visible paragraph boundaries inside otherwise valid marker beats."""

    refined: list[SemanticBeatPart] = []
    for part in parts:
        # A valid model marker already defines the beat. Refine it only when the
        # model also authored a real paragraph break; a single CRLF may merely
        # format one thought and must remain byte-for-byte inside that beat.
        visible_parts = _parts_from_authored_line_breaks(
            part.text,
            minimum_line_breaks=2,
        )
        for index, visible_part in enumerate(visible_parts):
            refined.append(
                SemanticBeatPart(
                    text=visible_part.text,
                    pause_before=(
                        part.pause_before
                        if index == 0
                        else visible_part.pause_before
                    ),
                )
            )
    return tuple(refined)


def parse_semantic_completion(raw: str, *, nonce: str) -> SemanticBeatPlan:
    """Validate nonce-scoped markers, then honor visible authored line breaks.

    Any candidate marker owned by this turn is removed before a rejected plan
    is returned, so malformed control text cannot leak into history or output.
    """

    candidate_matches = tuple(_ANY_MARKER_PATTERN.finditer(raw))
    owned_matches = tuple(_owned_marker_pattern(nonce).finditer(raw))
    clean_text = _remove_matches(raw, candidate_matches)

    if len(raw) > MAX_SEMANTIC_COMPLETION_CHARS:
        return _rejected(clean_text, "INPUT_TOO_LONG")

    exact_markers = {build_marker(nonce, pause): pause for pause in PauseClass}
    exact_pauses: list[PauseClass] = []
    malformed = False
    unknown_pause = False
    for match in owned_matches:
        exact_pause = exact_markers.get(match.group(0))
        if exact_pause is not None:
            exact_pauses.append(exact_pause)
            continue
        malformed = True
        pause_value = _pause_attribute_value(match.group(0))
        if pause_value is not None and pause_value not in PauseClass._value2member_map_:
            unknown_pause = True

    if unknown_pause:
        return _rejected(clean_text, "UNKNOWN_PAUSE")
    if malformed:
        return _rejected(clean_text, "MALFORMED_MARKER")
    if len(candidate_matches) > MAX_SEMANTIC_MARKERS:
        return _rejected(clean_text, "TOO_MANY_MARKERS")

    owned_spans = {match.span() for match in owned_matches}
    if any(match.span() not in owned_spans for match in candidate_matches):
        return _rejected(clean_text, "UNSCOPED_MARKER")

    protected_ranges = _protected_ranges(raw)
    if any(_overlaps(match.span(), protected) for match in owned_matches for protected in protected_ranges):
        return _rejected(clean_text, "MARKER_IN_PROTECTED_REGION")

    if not owned_matches:
        if not raw.strip():
            return _rejected(raw, "EMPTY_PART")
        return SemanticBeatPlan(
            clean_text=raw,
            parts=_parts_from_authored_line_breaks(raw),
            accepted=True,
        )

    parts: list[SemanticBeatPart] = []
    cursor = 0
    pause_before: PauseClass | None = None
    for match, following_pause in zip(owned_matches, exact_pauses, strict=True):
        parts.append(SemanticBeatPart(text=raw[cursor : match.start()], pause_before=pause_before))
        cursor = match.end()
        pause_before = following_pause
    parts.append(SemanticBeatPart(text=raw[cursor:], pause_before=pause_before))

    if any(not part.text.strip() for part in parts):
        return _rejected(clean_text, "EMPTY_PART")

    normalized_parts = _fold_punctuation_only_parts(parts, clean_text=clean_text)
    normalized_parts = _refine_parts_with_authored_line_breaks(normalized_parts)

    return SemanticBeatPlan(
        clean_text=clean_text,
        parts=normalized_parts,
        accepted=True,
    )


__all__ = [
    "MAX_SEMANTIC_COMPLETION_CHARS",
    "MAX_SEMANTIC_MARKERS",
    "PauseClass",
    "SEMANTIC_BEAT_NONCE_EXTRA",
    "SemanticBeatPart",
    "SemanticBeatPlan",
    "build_marker",
    "new_semantic_nonce",
    "parse_semantic_completion",
    "scrub_semantic_marker_candidates",
    "semantic_parts_from_visible_line_breaks",
    "semantic_beat_system_contract",
]
