"""Slice D exporter enhancement: lexicon-density projection for offline history.

The enhancement lets the encoded-dataset exporter fill observation channels
19-26 (the shallow text tone/engagement density channels) for *offline* history,
by reading each message body once through the single canonical ``v2core`` lexicon
and keeping only the bounded aggregate scalars -- the text itself never leaves.
Without it a real export fills only 3/36 channels and the label-free reaction
signal (which reads channels 25/26) has nothing to learn from.

PRIVACY: every dataset here is built from SYNTHETIC text -- inline message dicts
or a synthetic SQLite database created under ``tmp_path``. No test reads real
AstrBot history, sets ``ASTRBOT_DATA_DIR``, or opens any real data directory.

These tests pin, in order of the acceptance list:

* the derived channel values equal the lexicon read exactly (channels 19-26);
* absent/empty text degrades those channels to INVALID rather than a fabricated
  zero-density fact;
* the projection survives the record builder + writer, re-encodes bit-exactly,
  and leaks no message-text byte into the dataset;
* the real DB path (synthetic DB) projects densities and discards text;
* the manifest declares the channels the offline projection cannot fill (notably
  gap, channel 31), and a manifest that lies about that is rejected.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from scripts import v3_export
from sylanne_alpha.v2core.lexicon import read_signals


FIXTURE_DIR = Path(__file__).parent / "fixtures"
GATE_MANIFEST = FIXTURE_DIR / "v3_gate_manifest_v1.json"

# A synthetic body exercising every lexicon signal at once: warm (抱抱), cold (哼),
# distress (难过), a question (？), an exclamation (！) and punctuation.
RICH_TEXT = "抱抱你，但是哼，好难过！你还在吗？"

TONE_CHANNELS = (19, 20, 21, 22, 23, 24, 25, 26)
TEXT_CHANNELS = (18,) + TONE_CHANNELS


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


@pytest.fixture()
def link_key(tmp_path: Path) -> v3_export.EvaluationLinkKey:
    return v3_export.create_evaluation_link_key(tmp_path / "evaluation-link.key")


@pytest.fixture()
def exported(tmp_path: Path, link_key: v3_export.EvaluationLinkKey) -> v3_export.ExportResult:
    return v3_export.export_synthetic(
        output=tmp_path / "d.jsonl",
        manifest_path=tmp_path / "d.manifest.json",
        link_key=link_key,
        seed=99,
        groups=6,
        episodes_per_group=1,
        turns_per_episode=5,
    )


def _lexicon_expected(text: str) -> dict[int, float]:
    sig = read_signals(text)
    return {
        18: float(sig.length),
        19: float(sig.warm),
        20: float(sig.cold),
        21: float(sig.distress),
        22: 1.0 if sig.question else 0.0,
        23: float(sig.exclaim),
        24: float(sig.punct),
        25: float(sig.valence_cue),
        26: float(sig.engagement_cue),
    }


# --------------------------------------------------------------------------- #
# 1. Channels 19-26 equal the lexicon read exactly
# --------------------------------------------------------------------------- #


def test_project_messages_derives_tone_channels_from_the_v2core_lexicon() -> None:
    turns = v3_export._project_messages([{"role": "user", "content": RICH_TEXT}])
    assert len(turns) == 1
    turn = turns[0]

    expected = _lexicon_expected(RICH_TEXT)
    # The rich body must actually exercise the signals, or this asserts 0 == 0.
    assert expected[19] > 0 and expected[20] > 0 and expected[21] > 0
    assert expected[22] == 1.0 and expected[23] > 0 and expected[24] > 0

    for channel, value in expected.items():
        assert (turn.valid_mask >> channel) & 1, f"channel {channel} must be a stored fact"
        assert turn.values[channel] == value, f"channel {channel} must equal the lexicon read"

    # No offline fact exists for body.epoch (13) or gap_seconds (31): stay invalid.
    for channel in (13, 31):
        assert not (turn.valid_mask >> channel) & 1
        assert turn.values[channel] == 0.0


def test_zero_density_channels_stay_valid_for_nonempty_text() -> None:
    """A body with no warm words is a real observation of zero warm density.

    Offline records it as a valid zero-density fact (not INVALID), because 'no warm
    words' is a real observation.  NOTE: the live path does not actually fill 19-26
    at all (production capture leaves the tone fields ``None``), so this is offline
    behaviour, not a mirror of an online value -- see the exporter's module
    docstring "Real-history tone exposure".
    """

    text = "今天天气不错"  # no lexicon hits, no question, no punctuation
    turns = v3_export._project_messages([{"role": "user", "content": text}])
    turn = turns[0]
    expected = _lexicon_expected(text)
    for channel in TONE_CHANNELS:
        assert (turn.valid_mask >> channel) & 1, f"channel {channel} valid even at zero density"
        assert turn.values[channel] == expected[channel]


# --------------------------------------------------------------------------- #
# 1b. A >4096-char body must not leak its true length through the density
#     denominator (channel 18 saturates at 4096; densities re-normalize to it)
# --------------------------------------------------------------------------- #


def test_long_body_densities_are_normalized_by_the_clamped_length() -> None:
    """``read_signals`` divides counts by the TRUE length, but channel 18 saturates
    at 4096, so an unclamped density would let a holder reconstruct the true length
    of a >4096-char message and defeat channel 18's fingerprint clamp.  The exporter
    re-normalizes the count densities to the clamped length: two bodies with the
    same hit counts but different (both over-clamp) true lengths project identical
    densities, and channel 18 reports the clamp, not the true length."""

    clamp_len = v3_export.privacy_clamp(18, 1e9)  # the channel-18 saturation knee
    assert clamp_len == 4096.0
    filler = "x"  # ASCII: not a warm/cold/distress/punct char, not '?' or '!'
    hits = "抱抱" * 3  # identical warm-word hits in both bodies
    body_a = hits + filler * 5000   # true length 5006 > 4096
    body_b = hits + filler * 9000   # true length 9006 > 4096, same hit counts

    facts_a = v3_export._lexicon_channel_facts(body_a)
    facts_b = v3_export._lexicon_channel_facts(body_b)

    # Channel 18 reports the clamp, never the true length.
    assert facts_a[18] == clamp_len and facts_b[18] == clamp_len
    # Densities are identical -> the true length did not leak past the clamp.
    for channel in TONE_CHANNELS:
        assert facts_a[channel] == facts_b[channel], f"channel {channel} leaks true length"

    # The stored warm density equals count/clamped_length, not count/true_length,
    # and the raw (unclamped) density would have been strictly smaller.
    raw = read_signals(body_a)
    warm_count = round(raw.warm * raw.length / 10)
    assert warm_count > 0
    assert facts_a[19] == pytest.approx(warm_count * 10 / clamp_len)
    assert raw.warm < facts_a[19]


def test_short_body_density_projection_is_a_byte_exact_no_op() -> None:
    """For any body within the clamp the rescale is exactly 1.0, so the projection
    equals the raw lexicon read bit-for-bit (the common case is unchanged)."""

    facts = v3_export._lexicon_channel_facts(RICH_TEXT)
    expected = _lexicon_expected(RICH_TEXT)
    assert facts == expected


# --------------------------------------------------------------------------- #
# 2. Absent/empty text degrades to INVALID, never a fabricated zero
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("content", [None, 123, ["multimodal", "parts"], "", {"k": "v"}])
def test_absent_or_empty_text_leaves_text_channels_invalid(content: object) -> None:
    turns = v3_export._project_messages([{"role": "user", "content": content}])
    assert len(turns) == 1
    turn = turns[0]
    for channel in TEXT_CHANNELS:
        assert not (turn.valid_mask >> channel) & 1, f"channel {channel} must degrade to invalid"
        assert turn.values[channel] == 0.0
    # The structural history flag is not text-derived and remains a valid fact.
    assert (turn.valid_mask >> 30) & 1


# --------------------------------------------------------------------------- #
# 3. Survives export + re-encodes bit-exactly + leaks no text byte
# --------------------------------------------------------------------------- #


def _write_real_export(
    tmp_path: Path,
    link_key: v3_export.EvaluationLinkKey,
    messages: list,
    *,
    offline_unavailable_channels=None,
) -> tuple[Path, dict, list]:
    """Run the low-level real-history writer over a synthetic message list.

    Bypasses ``export_real_history`` (whose clean-tree gate is irrelevant here) so
    the projection -> records -> writer -> manifest path is exercised on synthetic
    text without a real database or a clean working tree.
    """

    if offline_unavailable_channels is None:
        offline_unavailable_channels = v3_export.OFFLINE_UNAVAILABLE_CHANNELS
    episode = v3_export.SourceEpisode(
        privacy_scope="LOCAL_HISTORY",
        session_identity="platform\x00user",
        ordinal=0,
        turns=v3_export._project_messages(messages),
    )
    source_key = b"\x11" * 32
    dataset_id = b"\x22" * 16
    digest = v3_export.default_gate_manifest_digest()
    rows = v3_export._build_records(
        [episode],
        link_key=link_key,
        source_key=source_key,
        dataset_id=dataset_id,
        provenance_class="REAL_LOCAL_HISTORY_V1",
        gate_manifest_digest=digest,
    )
    output = tmp_path / "real.jsonl"
    manifest = v3_export._write_export(
        rows,
        output=output,
        manifest_path=tmp_path / "real.manifest.json",
        link_key=link_key,
        source_key=source_key,
        source_key_id="source-test",
        dataset_id=dataset_id,
        provenance_class="REAL_LOCAL_HISTORY_V1",
        gate_manifest_digest=digest,
        source_corpus=b"synthetic-corpus",
        offline_unavailable_channels=offline_unavailable_channels,
    )
    return output, manifest, rows


def test_projected_densities_survive_export_and_reencode_exactly(tmp_path: Path, link_key) -> None:
    messages = [
        {"role": "user", "content": RICH_TEXT},
        {"role": "user", "content": "随便啦，哼。"},
    ]
    output, _manifest, rows = _write_real_export(tmp_path, link_key, messages)
    turn_rows = [row for row in rows if row["type"] == "turn"]
    assert len(turn_rows) == 2

    expected = _lexicon_expected(RICH_TEXT)
    first = turn_rows[0]
    for channel, value in expected.items():
        assert first["values"][channel] == value

    for row in turn_rows:
        v3_export.validate_row(row)
        frame = v3_export.frame_for_turn(row)
        again = v3_export.frame_for_turn(row)
        assert frame.values == again.values
        assert frame.valid_mask == again.valid_mask
        # every stored tone fact survives normalization into a valid encoded channel
        assert frame.valid_mask & v3_export.VALUE_CHANNEL_MASK == row["valid_mask"]

    # round-trips through the reader
    dataset = v3_export.read_dataset(output)
    assert dataset.episode_count == 1


def test_export_leaks_no_message_text_byte(tmp_path: Path, link_key) -> None:
    marker = "机密口令一二三"  # a recognizable non-lexicon substring
    messages = [
        {"role": "user", "content": RICH_TEXT + marker + "？"},
        {"role": "user", "content": "哼" + marker},
    ]
    output, manifest, _rows = _write_real_export(tmp_path, link_key, messages)
    blob = output.read_bytes() + json.dumps(manifest, ensure_ascii=False).encode("utf-8")
    for token in (marker, "抱抱", "难过", "哼", RICH_TEXT):
        assert token.encode("utf-8") not in blob, f"{token!r} leaked into the dataset"


# --------------------------------------------------------------------------- #
# 4. Real DB path (synthetic database) projects densities and discards text
# --------------------------------------------------------------------------- #


def _make_synthetic_db(tmp_path: Path, conversations: list[tuple]) -> Path:
    db_path = tmp_path / "data_v4.db"
    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            "CREATE TABLE conversations "
            "(conversation_id TEXT, platform_id TEXT, user_id TEXT, content TEXT, updated_at INTEGER)"
        )
        connection.executemany(
            "INSERT INTO conversations VALUES (?, ?, ?, ?, ?)", conversations
        )
        connection.commit()
    finally:
        connection.close()
    return db_path


def test_read_local_history_projects_densities_from_a_synthetic_database(tmp_path: Path) -> None:
    content = json.dumps(
        [
            {"role": "user", "content": RICH_TEXT},
            {"role": "assistant", "content": "ignored non-user turn"},
            {"role": "user", "content": "随便"},
        ],
        ensure_ascii=False,
    )
    _make_synthetic_db(
        tmp_path, [("conv-synth-1", "platform-synth", "user-synth", content, 1)]
    )

    episodes, corpus, _ = v3_export.read_local_history(tmp_path)
    assert len(episodes) == 1
    turns = episodes[0].turns
    assert len(turns) == 2  # only the two user messages become turns

    expected = _lexicon_expected(RICH_TEXT)
    for channel, value in expected.items():
        assert (turns[0].valid_mask >> channel) & 1
        assert turns[0].values[channel] == value
    # corpus digest ingredients are structural only, never the text.
    for token in ("抱抱", "难过", RICH_TEXT):
        assert token.encode("utf-8") not in corpus


# --------------------------------------------------------------------------- #
# 5. Manifest declares the offline-unavailable channels; a lie is rejected
# --------------------------------------------------------------------------- #


def test_synthetic_manifest_declares_no_offline_unavailable_channels(exported) -> None:
    assert exported.manifest["offline_unavailable_channels"] == []


def test_real_history_manifest_declares_gap_and_body_channels_unavailable(
    tmp_path: Path, link_key
) -> None:
    messages = [{"role": "user", "content": RICH_TEXT}, {"role": "user", "content": "哼。"}]
    output, manifest, _rows = _write_real_export(tmp_path, link_key, messages)

    declared = manifest["offline_unavailable_channels"]
    # gap (31) is the load-bearing one: the reaction decayer must treat it neutral.
    assert 31 in declared
    # the projection cannot fill any body.* channel offline either.
    assert set(declared) == set(v3_export.OFFLINE_UNAVAILABLE_CHANNELS)
    # the tone channels it DOES fill must not be declared unavailable.
    for channel in TONE_CHANNELS:
        assert channel not in declared

    v3_export.validate_manifest(manifest)
    # the honesty cross-check passes for a truthful manifest.
    v3_export.load_dataset_with_manifest(output, manifest)


@pytest.mark.parametrize(
    "bad",
    [[27], [36], [-1], [3, 3], [5, 2], [2.0], [True], "nope", 31],
)
def test_validate_manifest_rejects_a_malformed_offline_channel_list(exported, bad) -> None:
    with pytest.raises(v3_export.DatasetError, match="offline_unavailable"):
        v3_export.validate_manifest(dict(exported.manifest, offline_unavailable_channels=bad))


def test_load_rejects_a_manifest_that_hides_a_filled_channel_as_unavailable(
    tmp_path: Path, link_key
) -> None:
    """Declaring a channel the data actually fills would mislead the neutral path."""

    messages = [{"role": "user", "content": RICH_TEXT}]
    output, manifest, _rows = _write_real_export(tmp_path, link_key, messages)
    # channel 19 (text.warm) IS filled by RICH_TEXT -- claiming it unavailable lies.
    liar = dict(manifest, offline_unavailable_channels=[19])
    with pytest.raises(v3_export.DatasetError, match="offline-unavailable"):
        v3_export.load_dataset_with_manifest(output, liar)


def test_writer_refuses_to_emit_a_manifest_that_lies_about_unavailability(
    tmp_path: Path, link_key
) -> None:
    with pytest.raises(v3_export.DatasetError, match="offline-unavailable"):
        _write_real_export(
            tmp_path, link_key, [{"role": "user", "content": RICH_TEXT}],
            offline_unavailable_channels=(19,),  # 19 is filled -> writer must refuse
        )
