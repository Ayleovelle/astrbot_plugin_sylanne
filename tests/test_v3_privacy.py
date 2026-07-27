"""Task 15 privacy tests: nothing raw leaves the shadow, and no key leaks.

The v3 shadow only ever earns the right to run beside production because it is
structurally incapable of carrying host content out.  Three separate promises
back that claim, and each one is a different failure mode, so each is tested
against real bytes rather than against an intention:

1. *Cross-group isolation is a structural drop, not a policy note.*  When the
   bridge says cross-group facts are not allowed, ``build_group_view`` must
   return the empty view — not a fabricated, defaulted, or partially-cleared
   one.  A fabricated zero is worse than a refusal: it silently launders a fact
   the caller was never authorized to see.

2. *Opaque identity survives serialization.*  A raw ``unified_msg_origin`` that
   never appears in a ``repr()`` can still be sitting in the persisted state
   payload or the canonical trace.  These tests therefore scan the actual
   encoded bytes — including the *decompressed* state body, since a raw string
   hides perfectly from a scan of its own base64/zlib container — for the raw
   identifier and for the HMAC secret.

3. *Both HMAC keys fail closed and stay out of Git and the package.*  The
   runtime session key is tested for length-framing (so ``("qq","a:b")`` cannot
   alias ``("qq:a","b")``), for loss, for rotation, and for secret containment.
   The evaluation-link key is tested for file permissions, loss, and mismatch;
   the per-export source-digest key is tested for destruction.  Neither key may
   be tracked by Git or selected by the packager.

Only synthetic data and ``tmp_path`` are used here.  No test in this file reads
real AstrBot history, and the one exporter test that names a data directory
proves the refusal happens *before* any read.
"""

from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import zlib
from pathlib import Path

import pytest

from scripts import package_plugin, v3_export
from sylanne_alpha.v2core.shadow_snapshot import V2TurnObservationSnapshotV1
from sylanne_alpha.v3bridge.group_view_adapter import GROUP_VIEW_EMPTY, build_group_view
from sylanne_alpha.v3bridge.runtime_telemetry import RuntimeTelemetry, TelemetrySink
from sylanne_alpha.v3bridge.session_identity import (
    SessionIdentityKey,
    session_filename_token,
    session_trace_fields,
)
from sylanne_alpha.v3core import formula_v1 as formula
from sylanne_alpha.v3core.contracts import (
    Action,
    ComputeProfile,
    CoreInvocation,
    SessionRef,
    TurnContextClass,
    TurnEnvelope,
    TurnKey,
    TurnSequence,
)
from sylanne_alpha.v3core.orchestrator import orchestrate
from sylanne_alpha.v3core.state.codec import encode_state
from sylanne_alpha.v3core.state.models import V3State


# --------------------------------------------------------------------------- #
# The raw identity under test
# --------------------------------------------------------------------------- #

#: A deliberately distinctive origin: only a long, unique token can be scanned
#: for without false positives.  The platform id ("qq") is intentionally *not*
#: scanned for — two ASCII characters collide by chance in any base64 or hex
#: blob, so a scan for it would report noise rather than a leak.
_RAW_PLATFORM = "qq"
_RAW_ORIGIN = "aylovelle-1234567890"
_SECRET = b"privacy-test-session-secret-32b!"
_KEY_ID = "privacy-rotation-2026-07"


def _encodings(value: bytes) -> tuple[bytes, ...]:
    """Every spelling a leak could plausibly take in a serialized artifact."""

    return (value, value.hex().encode("ascii"), base64.b64encode(value))


_RAW_ENCODINGS = _encodings(_RAW_ORIGIN.encode("utf-8"))
_SECRET_ENCODINGS = _encodings(_SECRET)


def _assert_privacy_clean(label: str, blob: bytes) -> None:
    """Fail if a raw identifier or the HMAC secret survives into ``blob``."""

    for spelling in _RAW_ENCODINGS:
        assert spelling not in blob, f"{label} carries the raw session origin"
    for spelling in _SECRET_ENCODINGS:
        assert spelling not in blob, f"{label} carries the runtime HMAC secret"


def _state_body(blob: bytes) -> bytes:
    """The pre-compression state bytes.

    ``encode_state`` returns ``base64(zlib(payload))``.  Scanning only that
    container would pass even if the payload embedded the raw origin verbatim,
    because compression destroys the substring.  The real subject is the body.
    """

    return zlib.decompress(base64.b64decode(blob, validate=True))


def _trace_body(blob: bytes) -> bytes:
    """The packed trace bytes behind ``canonical_trace_bytes``' base64 container.

    Same trap as the state: base64 re-aligns every byte, so a raw identifier
    sitting in the packed body is invisible to a scan of the container.
    """

    return base64.b64decode(blob, validate=True)


# --------------------------------------------------------------------------- #
# Builders
# --------------------------------------------------------------------------- #


def _identity_key(key_id: str = _KEY_ID) -> SessionIdentityKey:
    return SessionIdentityKey(key_id=key_id, secret=_SECRET)


def _session_ref(session_generation: int = 3) -> SessionRef:
    ref = _identity_key().session_ref(
        _RAW_PLATFORM, _RAW_ORIGIN, session_generation=session_generation
    )
    assert ref is not None  # a complete identity must always match
    return ref


def _group_snapshot(scope: str) -> V2TurnObservationSnapshotV1:
    """An authoritative, fully-populated group fact view at one privacy scope."""

    return V2TurnObservationSnapshotV1(
        group_familiarity=0.75,
        group_engagement=0.5,
        group_tension=0.25,
        group_activity=0.875,
        group_valid_mask=0b1111,
        group_provenance="AUTHORITATIVE_TURN",
        group_source_revision=12,
        group_source_time=1000.0,
        group_privacy_scope=scope,
    )


def _raw_values() -> tuple:
    values: list[float | None] = [0.5] * 36
    for index in (27, 28, 29, 32, 33, 34, 35):
        values[index] = None  # derived channels must stay absent in facts
    values[30] = 1.0  # history_present bit (bool-coded)
    values[31] = 120.0  # gap seconds
    return tuple(values)


def _profile(name: str = "FULL_24_STDP") -> ComputeProfile:
    snn_enabled, ticks, stdp_enabled, reuse = formula.COMPUTE_PROFILES[name]
    return ComputeProfile(
        profile_id=name,
        snn_enabled=snn_enabled,
        ticks=ticks,
        stdp_enabled=stdp_enabled,
        reuse_last_summary=reuse,
        math_backend="scalar-v1",
        formula_version=formula.FORMULA_VERSION,
        model_version=formula.FORMULA_VERSION,
    )


def _invocation(ref: SessionRef, *, turn_id: str = "turn-000b") -> CoreInvocation:
    envelope = TurnEnvelope(
        turn_key=TurnKey(
            plugin_instance_id="plugin-instance",
            session_ref=ref,
            bridge_request_nonce="request-nonce",
            request_attempt=0,
        ),
        turn_id=turn_id,
        sequence=TurnSequence(writer_epoch=7, local_sequence=11),
        compute_profile=_profile(),
        deterministic_seed=b"d" * 16,
        observation=(_raw_values(), Action.SPEAK),
        context=TurnContextClass.ADDRESSED,
    )
    base = V3State(session_ref=ref, state_generation_id="gen-a", revision=4, writer_epoch=7)
    return CoreInvocation(
        envelope=envelope,
        base_state=base,
        projected_actual_outcome=(Action.SPEAK, None),
    )


def _telemetry(ref: SessionRef) -> RuntimeTelemetry:
    return RuntimeTelemetry(
        turn_id="turn-000b",
        session_key_id=ref.key_id,
        writer_epoch=7,
        plugin_instance_id="plugin-instance",
        outcome="COMMITTED",
        profile_id="FULL_24_STDP",
        profile_selection_reason="DEFAULT",
        load_level=1,
        queue_accepted=True,
        dropped=False,
        timed_out=False,
        commit_status="COMMITTED",
        cas_committed=True,
        retry_count=0,
        load_fill=0.25,
        stage_timings_us=(("encoder", 12.0),),
    )


# --------------------------------------------------------------------------- #
# 1. Cross-group-off isolation
# --------------------------------------------------------------------------- #


def test_cross_group_facts_are_dropped_whole_when_cross_group_is_not_allowed() -> None:
    view = build_group_view(_group_snapshot("CROSS_GROUP"), cross_group_allowed=False)

    assert view == GROUP_VIEW_EMPTY
    assert view.valid_mask == 0
    assert view.privacy_scope == "NONE"


@pytest.mark.parametrize("field", ["familiarity", "engagement", "tension", "activity"])
def test_cross_group_off_refuses_rather_than_fabricating_a_value(field: str) -> None:
    """A defaulted 0.0 would launder an unauthorized fact as a real observation.

    ``None`` says "not known"; ``0.0`` says "known to be zero". The adapter must
    never turn the second into the first.
    """

    view = build_group_view(_group_snapshot("CROSS_GROUP"), cross_group_allowed=False)

    assert getattr(view, field) is None


def test_cross_group_allowed_passes_the_authorized_facts_through() -> None:
    """Control: the drop must be caused by the flag, not by an inert adapter."""

    snapshot = _group_snapshot("CROSS_GROUP")
    view = build_group_view(snapshot, cross_group_allowed=True)

    assert view != GROUP_VIEW_EMPTY
    assert view.privacy_scope == "CROSS_GROUP"
    assert view.valid_mask == 0b1111
    assert (view.familiarity, view.engagement, view.tension, view.activity) == (
        snapshot.group_familiarity,
        snapshot.group_engagement,
        snapshot.group_tension,
        snapshot.group_activity,
    )


@pytest.mark.parametrize("scope", ["SESSION", "PERSON", "SAME_GROUP"])
def test_cross_group_off_only_clears_cross_group_scoped_facts(scope: str) -> None:
    """Turning cross-group off must not blind the shadow to in-scope facts."""

    view = build_group_view(_group_snapshot(scope), cross_group_allowed=False)

    assert view.privacy_scope == scope
    assert view.valid_mask == 0b1111


def test_group_view_drops_cross_group_facts_before_they_can_reach_a_digest() -> None:
    """The refusal is byte-level: the dropped magnitudes leave no residue."""

    dropped = build_group_view(_group_snapshot("CROSS_GROUP"), cross_group_allowed=False)
    allowed = build_group_view(_group_snapshot("CROSS_GROUP"), cross_group_allowed=True)

    assert "0.75" not in repr(dropped)
    assert "0.75" in repr(allowed)  # control: the value is visible when authorized


# --------------------------------------------------------------------------- #
# 2. Byte scans: filename token, trace fields, state bytes, trace, telemetry
# --------------------------------------------------------------------------- #


def test_session_filename_token_is_derived_only_from_the_opaque_ref() -> None:
    token = session_filename_token(_session_ref())

    assert re.fullmatch(r"s3-[0-9a-f]{64}", token)
    _assert_privacy_clean("session filename token", token.encode("utf-8"))


def test_session_trace_fields_carry_the_digest_and_nothing_else() -> None:
    ref = _session_ref()

    trace = session_trace_fields(ref)

    assert set(trace) == {"key_id", "session_digest", "session_generation"}
    assert trace["session_digest"] == ref.session_digest.hex()
    _assert_privacy_clean(
        "session trace fields", json.dumps(trace, sort_keys=True).encode("utf-8")
    )


def test_encoded_state_bytes_never_carry_the_raw_session_identifier() -> None:
    ref = _session_ref()
    invocation = _invocation(ref)

    result = orchestrate(invocation)

    assert result.accepted is True
    for label, state in (
        ("base state", invocation.base_state),
        ("committed next state", result.state_delta.next_state),
    ):
        blob = encode_state(state)
        _assert_privacy_clean(f"{label} container", blob)
        _assert_privacy_clean(f"{label} decompressed body", _state_body(blob))


def test_canonical_trace_bytes_never_carry_the_raw_session_identifier() -> None:
    result = orchestrate(_invocation(_session_ref()))

    assert result.accepted is True
    assert result.trace_bytes
    _assert_privacy_clean("canonical trace container", result.trace_bytes)
    _assert_privacy_clean("canonical trace body", _trace_body(result.trace_bytes))
    _assert_privacy_clean("core decision trace repr", repr(result.trace).encode("utf-8"))


def test_the_state_body_scan_can_actually_see_a_planted_identifier() -> None:
    """Guard the guard: a scan of the container alone would pass vacuously.

    If ``_state_body`` ever stopped decompressing, every state byte-scan above
    would silently become a no-op. Plant the raw origin in a field the codec
    really serializes and prove that only the body scan catches it.
    """

    leaky = V3State(
        session_ref=_session_ref(),
        state_generation_id=f"gen-{_RAW_ORIGIN}",  # a deliberate, local-only leak
        revision=4,
        writer_epoch=7,
    )
    blob = encode_state(leaky)

    _assert_privacy_clean("compressed container", blob)  # the container hides the leak
    with pytest.raises(AssertionError, match="raw session origin"):
        _assert_privacy_clean("planted leak", _state_body(blob))


def test_the_trace_body_scan_can_actually_see_a_planted_identifier() -> None:
    """The same guard for the trace, whose base64 container re-aligns every byte."""

    result = orchestrate(_invocation(_session_ref(), turn_id=f"turn-{_RAW_ORIGIN}"))

    assert result.accepted is True
    _assert_privacy_clean("base64 container", result.trace_bytes)  # container hides it
    with pytest.raises(AssertionError, match="raw session origin"):
        _assert_privacy_clean("planted leak", _trace_body(result.trace_bytes))


def test_runtime_telemetry_records_the_key_id_and_never_the_raw_session() -> None:
    ref = _session_ref()
    sink = TelemetrySink(capacity=4)

    sink.record(_telemetry(ref))

    assert sink.count == 1
    assert sink.last().session_key_id == _KEY_ID
    _assert_privacy_clean("telemetry record", repr(sink.last()).encode("utf-8"))
    _assert_privacy_clean("telemetry sink", repr(sink.recent()).encode("utf-8"))
    _assert_privacy_clean(
        "telemetry join key",
        repr(sink.last().join_key("gen-a", 5)).encode("utf-8"),
    )


# --------------------------------------------------------------------------- #
# 3. Runtime HMAC key: framing aliases, loss, rotation, permissions
# --------------------------------------------------------------------------- #


def test_length_framing_stops_a_platform_origin_boundary_alias() -> None:
    """Unframed concatenation would map both spellings to the same partition."""

    key = _identity_key()

    left = key.session_ref("qq", "a:b", session_generation=0)
    right = key.session_ref("qq:a", "b", session_generation=0)

    assert left is not None and right is not None
    assert left.session_digest != right.session_digest


@pytest.mark.parametrize(
    ("platform_id", "unified_msg_origin"),
    [(None, _RAW_ORIGIN), ("", _RAW_ORIGIN), (_RAW_PLATFORM, None), (_RAW_PLATFORM, "")],
)
def test_a_lost_identity_component_yields_no_ref_and_therefore_no_job(
    platform_id: object,
    unified_msg_origin: object,
) -> None:
    """Key loss must fail closed: no ref means the shadow never schedules work."""

    assert _identity_key().session_ref(
        platform_id, unified_msg_origin, session_generation=0
    ) is None


def test_key_rotation_repartitions_the_same_identity_and_is_carried_on_the_ref() -> None:
    rotated_id = "privacy-rotation-2026-08"

    original = _session_ref()
    rotated = _identity_key(rotated_id).session_ref(
        _RAW_PLATFORM, _RAW_ORIGIN, session_generation=3
    )

    assert rotated is not None
    assert original.session_digest != rotated.session_digest
    assert original.key_id == _KEY_ID
    assert rotated.key_id == rotated_id
    # The key_id travels with the ref, so a rotated partition is self-describing.
    assert session_trace_fields(rotated)["key_id"] == rotated_id


def test_the_session_secret_is_unrepresentable() -> None:
    key = _identity_key()
    ref = _session_ref()

    assert SessionIdentityKey.__dataclass_fields__["secret"].repr is False
    for label, rendered in (
        ("key repr", repr(key)),
        ("key str", str(key)),
        ("ref repr", repr(ref)),
        ("ref str", str(ref)),
    ):
        _assert_privacy_clean(label, rendered.encode("utf-8"))
        assert _SECRET.decode("ascii") not in rendered, f"{label} shows the secret"
    assert _KEY_ID in repr(key)  # control: the non-secret key_id is representable


# --------------------------------------------------------------------------- #
# 4. Evaluation-link key: permissions, loss, mismatch
# --------------------------------------------------------------------------- #


def _loosen_permissions(path: Path) -> None:
    """Grant world-read using the locale-independent Everyone SID (S-1-1-0).

    Windows ignores ``os.chmod`` for anything but the read-only flag, so the
    POSIX route would be a no-op there and the refusal test would pass without
    testing anything.
    """

    if os.name == "nt":
        result = subprocess.run(
            ["icacls", str(path), "/grant", "*S-1-1-0:R"], capture_output=True
        )
        assert result.returncode == 0, "icacls could not loosen the key file"
    else:
        os.chmod(path, 0o644)


def test_a_created_evaluation_link_key_is_permission_restricted(tmp_path: Path) -> None:
    path = tmp_path / "k.key"

    key = v3_export.create_evaluation_link_key(path)

    assert path.is_file()
    assert v3_export.key_file_is_restricted(path) is True
    assert v3_export.load_evaluation_link_key(path).secret == key.secret


def test_a_loosened_evaluation_link_key_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "k.key"
    v3_export.create_evaluation_link_key(path)

    _loosen_permissions(path)

    assert v3_export.key_file_is_restricted(path) is False
    with pytest.raises(v3_export.ExportRefused, match="restricted"):
        v3_export.load_evaluation_link_key(path)


def test_a_lost_evaluation_link_key_is_refused_not_regenerated(tmp_path: Path) -> None:
    """G4 must be INVALID_DATASET on loss; a silent re-mint would break G1/G3 linkage."""

    missing = tmp_path / "gone.key"

    assert v3_export.key_file_is_restricted(missing) is False
    with pytest.raises(v3_export.ExportRefused, match="missing"):
        v3_export.load_evaluation_link_key(missing)
    assert not missing.exists()


def test_creating_an_evaluation_link_key_never_overwrites_an_existing_one(
    tmp_path: Path,
) -> None:
    path = tmp_path / "k.key"
    original = v3_export.create_evaluation_link_key(path)

    with pytest.raises(v3_export.ExportRefused, match="overwrite"):
        v3_export.create_evaluation_link_key(path)

    assert v3_export.load_evaluation_link_key(path).secret == original.secret


def test_a_key_mismatch_between_two_campaigns_is_detectable(tmp_path: Path) -> None:
    """A G1/G3 key mismatch must show up as a digest *and* a grouping divergence."""

    first = v3_export.create_evaluation_link_key(tmp_path / "a.key")
    second = v3_export.create_evaluation_link_key(tmp_path / "b.key")
    scope, identity = "SYNTHETIC", "synthetic-session-7-0000"

    assert first.key_digest != second.key_digest
    assert first.evaluation_group_ref(scope, identity) != second.evaluation_group_ref(
        scope, identity
    )
    # The same key is stable, so the divergence above is the key and not noise.
    assert first.evaluation_group_ref(scope, identity) == first.evaluation_group_ref(
        scope, identity
    )
    assert re.fullmatch(r"[0-9a-f]{64}", first.evaluation_group_ref(scope, identity))


def test_the_published_synthetic_key_is_refused_for_a_real_export(tmp_path: Path) -> None:
    """The synthetic key is public, so grouping real history with it is an oracle.

    The data directory here is empty on purpose: the refusal must land on the
    key check *before* the exporter opens anything.
    """

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    output = tmp_path / "out.jsonl"

    with pytest.raises(v3_export.ExportRefused, match="synthetic"):
        v3_export.export_real_history(
            data_dir=data_dir,
            output=output,
            manifest_path=tmp_path / "out.manifest.json",
            link_key=v3_export.synthetic_link_key(1),
        )

    assert v3_export.synthetic_link_key(1).synthetic is True
    assert not output.exists()


# --------------------------------------------------------------------------- #
# 5. Source-digest key destruction
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="module")
def synthetic_export(tmp_path_factory: pytest.TempPathFactory) -> v3_export.ExportResult:
    """One small synthetic export; the corpus size is irrelevant to key handling."""

    root = tmp_path_factory.mktemp("synthetic-export")
    return v3_export.export_synthetic(
        output=root / "dataset.jsonl",
        manifest_path=root / "dataset.manifest.json",
        link_key=v3_export.synthetic_link_key(7),
        seed=7,
        groups=2,
        episodes_per_group=1,
        turns_per_episode=3,
    )


def test_the_per_export_source_digest_key_is_destroyed_at_freeze(
    synthetic_export: v3_export.ExportResult,
) -> None:
    manifest = synthetic_export.manifest

    assert synthetic_export.source_key_material is None
    assert manifest["source_digest_key_destroyed"] is True
    assert re.fullmatch(r"[0-9a-f]{64}", manifest["destroyed_source_key_digest"])
    # Only the digest survives: the id names the key, it does not reconstruct it.
    assert manifest["source_digest_key_id"].startswith("source-")


def test_the_written_manifest_records_the_destroyed_key_not_the_key(
    synthetic_export: v3_export.ExportResult,
) -> None:
    on_disk = json.loads(synthetic_export.manifest_path.read_text(encoding="utf-8"))

    assert on_disk["source_digest_key_destroyed"] is True
    assert on_disk["destroyed_source_key_digest"] == (
        synthetic_export.manifest["destroyed_source_key_digest"]
    )
    v3_export.validate_manifest(on_disk)


def test_the_encoded_dataset_carries_no_source_identity(
    synthetic_export: v3_export.ExportResult,
) -> None:
    """Traceable synthetic identities exist precisely so their absence is provable."""

    body = synthetic_export.output.read_bytes()

    assert synthetic_export.source_identifiers
    for identity in synthetic_export.source_identifiers:
        assert identity.encode("utf-8") not in body
    assert synthetic_export.source_corpus_bytes  # the corpus itself never ships
    assert synthetic_export.source_corpus_bytes not in body


# --------------------------------------------------------------------------- #
# 6. Neither evaluation key may enter Git or a package
# --------------------------------------------------------------------------- #


def test_the_evidence_tree_holding_both_keys_is_git_ignored() -> None:
    for name in ("evaluation-link.key", "source-digest.key", "dataset.jsonl"):
        assert v3_export.path_is_git_ignored(Path("artifacts/v3/evidence") / name) is True
    # Control: a tracked path must not be reported as ignored, or the check is inert.
    assert v3_export.path_is_git_ignored(Path("scripts/v3_export.py")) is False


def test_no_key_file_is_tracked_anywhere_in_git() -> None:
    tracked = subprocess.run(
        ["git", "ls-files", "*.key"],
        cwd=str(package_plugin.ROOT),
        capture_output=True,
        text=True,
        check=True,
    )

    assert tracked.stdout.strip() == "", f"a key file is tracked: {tracked.stdout!r}"


def test_the_packager_can_never_select_a_key_or_the_evidence_tree() -> None:
    """Assert the input-selection function itself; a built zip only samples it."""

    root = package_plugin.ROOT
    for relative in (
        Path("artifacts/v3/evidence/evaluation-link.key"),
        Path("artifacts/v3/evidence/dataset.jsonl"),
        Path("artifacts/evaluation-link.key"),
    ):
        assert package_plugin.should_include(root / relative) is False, relative

    assert "artifacts" not in package_plugin.INCLUDE_DIRS
    assert "artifacts" not in package_plugin.INCLUDE_ROOT_FILES
    # Control: a genuinely shipped input is still selected, so the rule above is
    # an exclusion and not a blanket refusal.
    assert package_plugin.should_include(root / "main.py") is True
    assert package_plugin.should_include(root / "sylanne_alpha" / "v3core" / "orchestrator.py") is True
