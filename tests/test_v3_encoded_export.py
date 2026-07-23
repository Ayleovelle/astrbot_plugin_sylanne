"""Task 15: the encoded evaluation dataset, its manifest, and every refusal.

`scripts/v3_export.py` is the only writer of an encoded evaluation dataset. It
reads local history exclusively from an *explicitly supplied* data directory,
performs the privacy projection **before** encoding, and never writes raw
content. These tests pin both halves of that contract:

* the positive shape — a tagged-union JSONL of `episode_header` / `turn` rows
  whose manifest fixes schema/formula/model revisions, provenance class, a
  random dataset ID, a *keyed* source-corpus digest, row count, episode/group/
  split digests, the evaluation-link key ID/digest, the destroyed source-key
  digest, the exporter commit, and the canonical exporter-source digest;
* the refusals — raw text/IDs, plain (unkeyed) source hashes, digest mismatch,
  missing/invalid initial-state headers, evaluation groups crossing a split,
  ambiguous gaps, mutable provenance, and any record outside the tagged schema.

No test here reads real AstrBot history: every dataset is built from the
synthetic corpus so the suite is safe to run anywhere.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts import v3_export


FIXTURE_DIR = Path(__file__).parent / "fixtures"
DATASET = FIXTURE_DIR / "v3_replay_synthetic_v1.jsonl"
MANIFEST = FIXTURE_DIR / "v3_replay_synthetic_v1.manifest.json"
GATE_MANIFEST = FIXTURE_DIR / "v3_gate_manifest_v1.json"


# --------------------------------------------------------------------------- #
# Builders
# --------------------------------------------------------------------------- #


@pytest.fixture()
def link_key(tmp_path: Path) -> v3_export.EvaluationLinkKey:
    return v3_export.create_evaluation_link_key(tmp_path / "evaluation-link.key")


@pytest.fixture()
def exported(tmp_path: Path, link_key: v3_export.EvaluationLinkKey) -> v3_export.ExportResult:
    """A small synthetic export, produced exactly like the tracked fixture."""

    return v3_export.export_synthetic(
        output=tmp_path / "d.jsonl",
        manifest_path=tmp_path / "d.manifest.json",
        link_key=link_key,
        seed=99,
        groups=6,
        episodes_per_group=1,
        turns_per_episode=5,
    )


def _rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


# --------------------------------------------------------------------------- #
# Tagged union shape
# --------------------------------------------------------------------------- #


def test_dataset_is_a_tagged_union_of_only_declared_record_types(exported) -> None:
    rows = _rows(exported.output)
    assert rows, "export produced no rows"
    assert {row["type"] for row in rows} == {"episode_header", "turn"}
    for row in rows:
        assert row["type"] in v3_export.RECORD_TYPES
        expected = (
            v3_export.EPISODE_HEADER_FIELDS
            if row["type"] == "episode_header"
            else v3_export.TURN_FIELDS
        )
        assert set(row) == set(expected), f"{row['type']} has fields outside the tagged schema"


def test_every_episode_header_carries_the_frozen_neutral_initial_state(exported) -> None:
    headers = [row for row in _rows(exported.output) if row["type"] == "episode_header"]
    assert headers
    for header in headers:
        assert header["initial_state_id"] == v3_export.INITIAL_STATE_ID == "neutral_eval_v2"
        payload = header["initial_state_b64"].encode("ascii")
        assert hashlib.sha256(payload).hexdigest() == header["initial_state_digest"]
        # The header state is the canonical neutral state, identical for every episode.
        assert header["initial_state_digest"] == v3_export.neutral_eval_state_digest()
        assert header["pending_credit_censored"] is True
        assert header["evaluation_profile_id"] == "FORMULA_V2_SCALAR"
        assert header["gate_manifest_digest"] == exported.manifest["gate_manifest_digest"]
        assert len(bytes.fromhex(header["episode_seed"])) == 16  # first 128 bits


def test_turn_rows_carry_the_declared_evaluation_fields(exported) -> None:
    turns = [row for row in _rows(exported.output) if row["type"] == "turn"]
    assert turns
    for turn in turns:
        assert len(turn["values"]) == 36
        assert all(isinstance(value, float) for value in turn["values"])
        assert 0 <= turn["valid_mask"] < (1 << 36)
        assert turn["context"] in ("ADDRESSED", "AMBIENT", "PROACTIVE", "IDLE")
        assert turn["actual_action"] in ("SPEAK", "HOLD", "CLARIFY", "REACH", "UNKNOWN")
        assert isinstance(turn["credit_adjacency"], bool)
        assert turn["dropped_gap_count"] >= 0
        assert len(bytes.fromhex(turn["source_record_digest"])) == 32
        assert turn["row_digest"] == v3_export.row_digest(turn)


def test_derived_channels_are_never_stored_as_facts(exported) -> None:
    """27-29/32-35 are derived by the encoder from context and the resolved action."""

    for turn in [row for row in _rows(exported.output) if row["type"] == "turn"]:
        for channel in (27, 28, 29, 32, 33, 34, 35):
            assert not (turn["valid_mask"] >> channel) & 1
            assert turn["values"][channel] == 0.0


def test_stored_rows_reconstruct_their_observation_frame_exactly(exported) -> None:
    """The stored facts must re-encode bit-exactly: replay may not drift from export."""

    for turn in [row for row in _rows(exported.output) if row["type"] == "turn"]:
        frame = v3_export.frame_for_turn(turn)
        again = v3_export.frame_for_turn(turn)
        assert frame.values == again.values
        assert frame.valid_mask == again.valid_mask
        # every stored fact bit survives normalization
        assert frame.valid_mask & v3_export.VALUE_CHANNEL_MASK == turn["valid_mask"]


# --------------------------------------------------------------------------- #
# Manifest
# --------------------------------------------------------------------------- #


def test_manifest_fixes_every_declared_field(exported) -> None:
    manifest = exported.manifest
    for field in v3_export.MANIFEST_FIELDS:
        assert field in manifest, f"manifest is missing {field}"
    assert manifest["schema"] == v3_export.DATASET_SCHEMA
    assert manifest["provenance_class"] in v3_export.PROVENANCE_CLASSES
    assert manifest["row_count"] == len(_rows(exported.output))
    assert len(bytes.fromhex(manifest["dataset_id"])) == 16
    assert manifest["source_digest_key_destroyed"] is True
    assert manifest["evaluation_link_key_id"]
    assert len(bytes.fromhex(manifest["exporter_source_digest"])) == 32


def test_dataset_id_is_random_per_export(tmp_path: Path, link_key) -> None:
    first = v3_export.export_synthetic(
        output=tmp_path / "a.jsonl", manifest_path=tmp_path / "a.manifest.json",
        link_key=link_key, seed=5, groups=3, episodes_per_group=1, turns_per_episode=3,
    )
    second = v3_export.export_synthetic(
        output=tmp_path / "b.jsonl", manifest_path=tmp_path / "b.manifest.json",
        link_key=link_key, seed=5, groups=3, episodes_per_group=1, turns_per_episode=3,
    )
    assert first.manifest["dataset_id"] != second.manifest["dataset_id"]


def test_same_link_key_gives_stable_groups_and_splits_across_exports(tmp_path: Path, link_key) -> None:
    """G1 and G3 must agree on evaluation groups/splits for the same scope."""

    first = v3_export.export_synthetic(
        output=tmp_path / "a.jsonl", manifest_path=tmp_path / "a.manifest.json",
        link_key=link_key, seed=5, groups=3, episodes_per_group=1, turns_per_episode=3,
    )
    second = v3_export.export_synthetic(
        output=tmp_path / "b.jsonl", manifest_path=tmp_path / "b.manifest.json",
        link_key=link_key, seed=5, groups=3, episodes_per_group=1, turns_per_episode=3,
    )
    assert first.manifest["groups_digest"] == second.manifest["groups_digest"]
    assert first.manifest["splits_digest"] == second.manifest["splits_digest"]
    # ... but a different link key must not reproduce the same grouping.
    other = v3_export.create_evaluation_link_key(tmp_path / "other.key")
    third = v3_export.export_synthetic(
        output=tmp_path / "c.jsonl", manifest_path=tmp_path / "c.manifest.json",
        link_key=other, seed=5, groups=3, episodes_per_group=1, turns_per_episode=3,
    )
    assert third.manifest["groups_digest"] != first.manifest["groups_digest"]


def test_source_corpus_digest_is_keyed_and_the_plain_hash_never_appears(exported) -> None:
    """A plain source hash is a re-identification oracle; only a keyed digest may ship."""

    plain = hashlib.sha256(exported.source_corpus_bytes).hexdigest()
    blob = exported.output.read_bytes() + json.dumps(exported.manifest).encode("utf-8")
    assert plain.encode("ascii") not in blob
    assert exported.manifest["source_corpus_digest"] != plain
    assert len(bytes.fromhex(exported.manifest["source_corpus_digest"])) == 32


def test_destroyed_source_key_is_recorded_by_digest_and_not_retained(exported) -> None:
    assert exported.manifest["destroyed_source_key_digest"]
    assert exported.source_key_material is None, "the source-digest key must be destroyed"
    blob = exported.output.read_bytes() + json.dumps(exported.manifest).encode("utf-8")
    assert exported.manifest["destroyed_source_key_digest"].encode("ascii") in blob


# --------------------------------------------------------------------------- #
# Refusals
# --------------------------------------------------------------------------- #


def test_export_rejects_raw_text_and_raw_identifiers(tmp_path: Path, link_key) -> None:
    with pytest.raises(v3_export.PrivacyViolation, match="raw"):
        v3_export.assert_no_raw_content({"type": "turn", "text": "hello world"})
    with pytest.raises(v3_export.PrivacyViolation):
        v3_export.assert_no_raw_content({"type": "turn", "session_id": "qq:12345"})


def test_exported_bytes_contain_no_synthetic_source_identifier(exported) -> None:
    blob = exported.output.read_bytes()
    for marker in exported.source_identifiers:
        assert marker.encode("utf-8") not in blob, f"{marker!r} leaked into the dataset"


def test_replay_rejects_a_row_whose_digest_does_not_match(exported) -> None:
    rows = _rows(exported.output)
    turn = next(row for row in rows if row["type"] == "turn")
    turn["values"] = [0.0] * 36
    with pytest.raises(v3_export.DatasetError, match="row_digest"):
        v3_export.validate_row(turn)


def test_reader_rejects_a_missing_or_invalid_initial_state_header(tmp_path: Path, exported) -> None:
    rows = _rows(exported.output)
    headerless = [row for row in rows if row["type"] != "episode_header"]
    path = tmp_path / "headerless.jsonl"
    path.write_text("\n".join(json.dumps(row) for row in headerless), encoding="utf-8")
    with pytest.raises(v3_export.DatasetError, match="header"):
        v3_export.read_dataset(path)

    # Re-sign the tampered header: an unsigned edit would trip the row digest first
    # and never exercise the initial-state gate we are actually testing here.
    bad = list(rows)
    header_index = next(i for i, row in enumerate(bad) if row["type"] == "episode_header")
    tampered = dict(bad[header_index], initial_state_digest="0" * 64)
    tampered["row_digest"] = v3_export.row_digest(tampered)
    bad[header_index] = tampered
    path2 = tmp_path / "badstate.jsonl"
    path2.write_text("\n".join(json.dumps(row) for row in bad), encoding="utf-8")
    with pytest.raises(v3_export.DatasetError, match="initial_state"):
        v3_export.read_dataset(path2)


def test_reader_rejects_an_evaluation_group_that_crosses_a_split(tmp_path: Path, exported) -> None:
    rows = _rows(exported.output)
    headers = [row for row in rows if row["type"] == "episode_header"]
    victim = headers[0]
    flipped = "dev" if victim["split"] != "dev" else "test"
    # The clone must be internally consistent (valid derived seed for its new
    # episode_ref) so the SPLIT is the only thing wrong; otherwise the seed gate
    # fires first and this test would never exercise the cross-split guard.
    episode_ref = "f" * 64
    clone = dict(victim, episode_ref=episode_ref, split=flipped)
    clone["episode_seed"] = v3_export.episode_seed(
        dataset_id=bytes.fromhex(clone["dataset_id"]),
        evaluation_group_ref=bytes.fromhex(clone["evaluation_group_ref"]),
        episode_ref=bytes.fromhex(episode_ref),
        gate_manifest_digest=bytes.fromhex(clone["gate_manifest_digest"]),
        formula_digest=bytes.fromhex(clone["formula_digest"]),
        model_digest=bytes.fromhex(clone["model_digest"]),
        profile_digest=bytes.fromhex(clone["evaluation_profile_digest"]),
    ).hex()
    clone["row_digest"] = v3_export.row_digest(clone)
    path = tmp_path / "crosssplit.jsonl"
    path.write_text("\n".join(json.dumps(row) for row in rows + [clone]), encoding="utf-8")
    with pytest.raises(v3_export.DatasetError, match="split"):
        v3_export.read_dataset(path)


def test_reader_rejects_an_ambiguous_gap(tmp_path: Path, exported) -> None:
    """A turn cannot both claim adjacent credit and admit a dropped gap."""

    rows = _rows(exported.output)
    index = next(i for i, row in enumerate(rows) if row["type"] == "turn")
    bad = dict(rows[index], credit_adjacency=True, dropped_gap_count=3)
    bad["row_digest"] = v3_export.row_digest(bad)
    rows[index] = bad
    path = tmp_path / "gap.jsonl"
    path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
    with pytest.raises(v3_export.DatasetError, match="gap"):
        v3_export.read_dataset(path)


def test_reader_rejects_a_mutable_provenance_class(tmp_path: Path, exported) -> None:
    with pytest.raises(v3_export.DatasetError, match="provenance"):
        v3_export.validate_manifest(dict(exported.manifest, provenance_class="whatever-i-like"))


def test_reader_rejects_any_record_outside_the_tagged_schema(tmp_path: Path, exported) -> None:
    rows = _rows(exported.output)
    rows.append({"type": "note", "comment": "free-form"})
    path = tmp_path / "extra.jsonl"
    path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
    with pytest.raises(v3_export.DatasetError, match="type"):
        v3_export.read_dataset(path)


def test_reader_rejects_a_turn_with_an_unknown_extra_field(tmp_path: Path, exported) -> None:
    rows = _rows(exported.output)
    index = next(i for i, row in enumerate(rows) if row["type"] == "turn")
    rows[index] = dict(rows[index], raw_text="hi")
    path = tmp_path / "extrafield.jsonl"
    path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
    with pytest.raises(v3_export.DatasetError):
        v3_export.read_dataset(path)


def test_manifest_digest_mismatch_is_rejected(tmp_path: Path, exported) -> None:
    with pytest.raises(v3_export.DatasetError, match="dataset_digest"):
        v3_export.load_dataset_with_manifest(
            exported.output, dict(exported.manifest, dataset_digest="0" * 64)
        )


def test_canonical_text_digest_is_line_ending_invariant(tmp_path: Path) -> None:
    """Git's checkout EOL policy must not change a tracked artifact's identity."""

    lf = tmp_path / "lf.txt"
    crlf = tmp_path / "crlf.txt"
    cr = tmp_path / "cr.txt"
    lf.write_bytes(b"alpha\nbeta\n")
    crlf.write_bytes(b"alpha\r\nbeta\r\n")
    cr.write_bytes(b"alpha\rbeta\r")

    expected = hashlib.sha256(b"alpha\nbeta\n").hexdigest()
    assert v3_export.canonical_text_digest(lf) == expected
    assert v3_export.canonical_text_digest(crlf) == expected
    assert v3_export.canonical_text_digest(cr) == expected
    assert v3_export.file_digest(lf) == expected
    assert v3_export.file_digest(crlf) == expected
    assert v3_export.file_digest(cr) == expected


def test_dataset_digest_accepts_equivalent_lf_and_crlf_checkouts(
    tmp_path: Path,
    exported,
) -> None:
    """A manifest generated on either OS must validate after Git EOL conversion."""

    canonical = exported.output.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    lf = tmp_path / "fixture-lf.jsonl"
    crlf = tmp_path / "fixture-crlf.jsonl"
    lf.write_bytes(canonical)
    crlf.write_bytes(canonical.replace(b"\n", b"\r\n"))

    v3_export.load_dataset_with_manifest(lf, exported.manifest)
    v3_export.load_dataset_with_manifest(crlf, exported.manifest)


def test_export_writes_canonical_lf_jsonl(exported) -> None:
    payload = exported.output.read_bytes()
    assert payload.endswith(b"\n")
    assert b"\r" not in payload


def test_export_refuses_a_data_directory_that_was_not_explicitly_supplied() -> None:
    with pytest.raises(v3_export.ExportRefused, match="explicit"):
        v3_export.resolve_data_dir(None)


# --------------------------------------------------------------------------- #
# Bug fix (Slice D): offline history length is text.length (ch18), not body.epoch
# (ch13).  Both channels share the _log_length normalizer, so the old misplacement
# never crashed -- it just fed the reaction signal's length channel (18) a constant
# 0 while polluting the body.epoch slot (13) with the message length.
# --------------------------------------------------------------------------- #


def test_project_messages_stores_length_in_text_length_channel_18_not_body_epoch_13() -> None:
    messages = [
        {"role": "user", "content": "hello"},  # length 5
        {"role": "assistant", "content": "ignored non-user turn"},
        {"role": "user", "content": "a rather longer user message"},  # length 28
    ]
    turns = v3_export._project_messages(messages)
    assert len(turns) == 2  # only the two user turns become turns
    for turn, expected_length in zip(turns, (5.0, 28.0)):
        # text.length (channel 18) carries THIS message's own length.
        assert (turn.valid_mask >> 18) & 1, "channel 18 (text.length) must be a stored fact"
        assert turn.values[18] == expected_length
        # channel 13 is body.epoch -- offline history has no epoch fact, so it must
        # stay invalid and zero, never smuggle a text length.
        assert not (turn.valid_mask >> 13) & 1, "channel 13 (body.epoch) is never a text length"
        assert turn.values[13] == 0.0


def test_project_messages_length_survives_export_into_channel_18(tmp_path: Path, link_key) -> None:
    """End-to-end: a real-shaped projection stores the length under channel 18."""

    episode = v3_export.SourceEpisode(
        privacy_scope="LOCAL_HISTORY",
        session_identity="platform\x00user",
        ordinal=0,
        turns=v3_export._project_messages(
            [{"role": "user", "content": "x" * 40}, {"role": "user", "content": "y" * 12}]
        ),
    )
    rows = v3_export._build_records(
        [episode],
        link_key=link_key,
        source_key=b"\x11" * 32,
        dataset_id=b"\x22" * 16,
        provenance_class="REAL_LOCAL_HISTORY_V1",
        gate_manifest_digest=v3_export.default_gate_manifest_digest(),
    )
    turn_rows = [row for row in rows if row["type"] == "turn"]
    for turn_row, expected_length in zip(turn_rows, (40.0, 12.0)):
        v3_export.validate_row(turn_row)  # must satisfy the frozen turn schema
        assert (turn_row["valid_mask"] >> 18) & 1
        assert turn_row["values"][18] == expected_length
        assert not (turn_row["valid_mask"] >> 13) & 1


# --------------------------------------------------------------------------- #
# Seed derivation (design 17.2 / plan "Planned Files")
# --------------------------------------------------------------------------- #


def test_episode_seed_matches_the_declared_domain_separated_formula() -> None:
    parts = dict(
        dataset_id=bytes.fromhex("ab" * 16),
        evaluation_group_ref=bytes.fromhex("cd" * 32),
        episode_ref=bytes.fromhex("ef" * 32),
        gate_manifest_digest=bytes.fromhex("12" * 32),
        formula_digest=bytes.fromhex("34" * 32),
        model_digest=bytes.fromhex("56" * 32),
        profile_digest=bytes.fromhex("78" * 32),
    )
    expected = hashlib.sha256(
        b"SYL3\x01EVAL\x00" + b"".join(v3_export.framed(parts[name]) for name in v3_export.EPISODE_SEED_ORDER)
    ).digest()[:16]
    assert v3_export.episode_seed(**parts) == expected


def test_control_seed_only_appends_the_framed_control_id() -> None:
    parts = dict(
        dataset_id=bytes.fromhex("ab" * 16),
        evaluation_group_ref=bytes.fromhex("cd" * 32),
        episode_ref=bytes.fromhex("ef" * 32),
        gate_manifest_digest=bytes.fromhex("12" * 32),
        formula_digest=bytes.fromhex("34" * 32),
        model_digest=bytes.fromhex("56" * 32),
        profile_digest=bytes.fromhex("78" * 32),
    )
    base = b"".join(v3_export.framed(parts[name]) for name in v3_export.EPISODE_SEED_ORDER)
    expected = hashlib.sha256(
        b"SYL3\x01EVAL\x00" + base + v3_export.framed(b"label_free_frozen")
    ).digest()[:16]
    assert v3_export.control_episode_seed(control_id="label_free_frozen", **parts) == expected
    assert v3_export.CONTROL_IDS == ("label_free_on", "label_free_frozen")
    # controls must not collide with the unmodified stream or with each other
    seeds = {
        v3_export.control_episode_seed(control_id=name, **parts)
        for name in v3_export.CONTROL_IDS
    }
    assert len(seeds) == 2
    assert v3_export.episode_seed(**parts) not in seeds


def test_turn_seed_never_changes_the_episode_seed() -> None:
    base = bytes.fromhex("9a" * 16)
    expected = hashlib.sha256(
        b"SYL3\x01EVALTURN\x00" + v3_export.framed(base) + v3_export.framed((7).to_bytes(8, "big"))
    ).digest()[:16]
    assert v3_export.evaluation_turn_seed(base, 7) == expected
    assert v3_export.evaluation_turn_seed(base, 7) != v3_export.evaluation_turn_seed(base, 8)


def test_length_framing_is_not_ambiguous() -> None:
    assert v3_export.framed(b"a") + v3_export.framed(b"bc") != v3_export.framed(b"ab") + v3_export.framed(b"c")


# --------------------------------------------------------------------------- #
# The tracked synthetic fixture
# --------------------------------------------------------------------------- #


def test_tracked_synthetic_fixture_is_valid_and_synthetic() -> None:
    dataset = v3_export.read_dataset(DATASET)
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    v3_export.validate_manifest(manifest)
    v3_export.load_dataset_with_manifest(DATASET, manifest)
    assert manifest["provenance_class"] == "SYNTHETIC_V1"
    assert manifest["gate_manifest_digest"] == v3_export.file_digest(GATE_MANIFEST)
    assert dataset.episode_count >= 6
    assert {episode.split for episode in dataset.episodes} == {"train", "dev", "test"}


def test_tracked_fixture_was_produced_by_this_exporter() -> None:
    """A fixture built by a different exporter may not reflect current behaviour.

    The commit field is deliberately NOT asserted: it truthfully names the HEAD at
    generation time and would break on every later commit. The source digest is
    content-addressed, so staleness here is real staleness.
    """

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert manifest["exporter_source_digest"] == v3_export.exporter_source_digest(), (
        "tests/fixtures/v3_replay_synthetic_v1.jsonl is stale: regenerate it with "
        "scripts/v3_export.py --synthetic after changing the exporter"
    )
    assert manifest["exporter_source_digest"] == v3_export.canonical_text_digest(
        Path(v3_export.__file__)
    )


def test_tracked_fixture_never_lets_an_evaluation_group_cross_a_split() -> None:
    dataset = v3_export.read_dataset(DATASET)
    by_group: dict[str, set[str]] = {}
    for episode in dataset.episodes:
        by_group.setdefault(episode.evaluation_group_ref, set()).add(episode.split)
    assert all(len(splits) == 1 for splits in by_group.values())


def test_tracked_fixture_has_multi_episode_groups_so_the_split_guard_can_fail() -> None:
    """The guard exists for groups contributing >1 episode (spec 17.2).

    With one episode per group the cross-split assertion is structurally
    unfalsifiable: a `split_for` that returned a random value per call would pass
    it. The fixture must contain the only case the guard is for.
    """

    dataset = v3_export.read_dataset(DATASET)
    counts: dict[str, int] = {}
    for episode in dataset.episodes:
        counts[episode.evaluation_group_ref] = counts.get(episode.evaluation_group_ref, 0) + 1
    assert max(counts.values()) >= 2, "no group contributes >1 episode: the split guard is vacuous"


def test_split_assignment_is_a_pure_function_of_the_group_reference(link_key) -> None:
    """A per-call random split would satisfy every cross-split assertion."""

    group = link_key.evaluation_group_ref("SYNTHETIC", "identity-a")
    assert len({link_key.split_for(group) for _ in range(50)}) == 1
    # ...and it must actually depend on the group, not be a constant.
    groups = {link_key.evaluation_group_ref("SYNTHETIC", f"id-{i}") for i in range(60)}
    assert len({link_key.split_for(g) for g in groups}) > 1


def test_reader_rejects_a_hand_picked_episode_seed(tmp_path: Path, exported) -> None:
    """A re-signed header must not be able to pin an attacker-chosen seed."""

    rows = _rows(exported.output)
    index = next(i for i, row in enumerate(rows) if row["type"] == "episode_header")
    tampered = dict(rows[index], episode_seed="00" * 16)
    tampered["row_digest"] = v3_export.row_digest(tampered)
    rows[index] = tampered
    path = tmp_path / "seed.jsonl"
    path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
    with pytest.raises(v3_export.DatasetError, match="episode_seed"):
        v3_export.read_dataset(path)


def test_reader_rejects_a_nonzero_value_in_a_masked_off_channel(tmp_path: Path, exported) -> None:
    """A slot replay ignores and no privacy scan reads is a covert channel."""

    rows = _rows(exported.output)
    index = next(
        i for i, row in enumerate(rows)
        if row["type"] == "turn" and (~row["valid_mask"]) & v3_export.VALUE_CHANNEL_MASK
    )
    turn = rows[index]
    channel = next(
        c for c in v3_export.VALUE_CHANNELS if not (turn["valid_mask"] >> c) & 1
    )
    values = list(turn["values"])
    values[channel] = 0.5
    tampered = dict(turn, values=values)
    tampered["row_digest"] = v3_export.row_digest(tampered)
    rows[index] = tampered
    path = tmp_path / "covert.jsonl"
    path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
    with pytest.raises(v3_export.DatasetError, match="masked off"):
        v3_export.read_dataset(path)


def test_stored_facts_are_clamped_to_the_encoders_saturation_range(exported) -> None:
    """A stored fact must not distinguish inputs the frame would collapse."""

    for turn in [row for row in _rows(exported.output) if row["type"] == "turn"]:
        for channel, (low, high) in v3_export.PRIVACY_CLAMPS.items():
            if (turn["valid_mask"] >> channel) & 1:
                assert low <= turn["values"][channel] <= high


def test_unimplemented_g3_flags_refuse_instead_of_silently_ignoring(tmp_path: Path) -> None:
    """A parsed flag that does nothing lets G4 believe a contract never applied."""

    for flag in ("--only-provable-correlation", "--require-build-channel"):
        argv = [
            "--astrbot-data-dir", str(tmp_path),
            "--evaluation-link-key", str(tmp_path / "k.key"),
            "--output", str(tmp_path / "o.jsonl"),
            "--manifest", str(tmp_path / "o.json"),
            flag, *(["grey"] if flag == "--require-build-channel" else []),
        ]
        with pytest.raises(v3_export.ExportRefused, match="NOT IMPLEMENTED"):
            v3_export.main(argv)


def test_no_evaluation_key_is_tracked_by_git() -> None:
    """Neither evaluation key may enter Git or a package."""

    assert v3_export.path_is_git_ignored(Path("artifacts/v3/evidence/evaluation-link.key"))
    assert v3_export.path_is_git_ignored(Path("artifacts/v3/evidence/g1/real-history-v1.jsonl"))
