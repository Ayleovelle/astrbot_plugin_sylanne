"""Encoded v3 evaluation dataset exporter (plan Task 15, design 17.2).

This is the *only* writer of an encoded evaluation dataset. It reads local
history exclusively from an explicitly supplied data directory, performs the
privacy projection **before** encoding, and never writes raw content: no text,
no identifiers, no prompts, no replies, no memory strings, no plain source
hashes, no secrets, and no unhashed source paths.

Dataset format
--------------
A JSONL *tagged union* of two record types:

``episode_header``
    schema/provenance, random dataset ID, evaluation-group reference, episode
    reference, split, canonical ``neutral_eval_v2`` initial-state bytes/digest,
    boundary-censored pending credit, fixed evaluation-profile ID/digest,
    gate-manifest digest, and the episode seed.

``turn``
    episode reference/index, 36 privacy-normalized channel facts, a 36-bit
    validity mask, context class, actual action, sequence, ``credit_adjacency``,
    dropped/unmatched-gap count, observed profile ID/digest when available, a
    keyed source-record digest, and the row digest.

Why the stored 36 values are encoder *inputs*, not encoder *outputs*
--------------------------------------------------------------------
**This is a deviation from the plan text and needs an architect ruling.** The plan
says a turn carries "36 normalized values, 36-bit validity mask", which reads as
``ObservationFrame`` — and ``ObservationFrame`` would reject what is stored here,
because raw lengths/gaps are not in [0,1].

The reason for the deviation is narrow and mechanical: ``orchestrate()`` accepts
only ``(raw_values, previous_action)`` and re-runs ``encode_observation`` itself.
It has **no frame entry point**. Rebuilding an ``ObservationFrame`` from stored
output is trivially bit-exact, but there is no way to *feed* one to the real
pipeline without changing the core, which is outside this task's declared files.
Recovering raw facts by inverting the encoder is not a way out either: the
normalizers are saturating and non-injective, so ``encode(invert(v)) != v`` for a
measurable fraction of values, and ``encode.invert`` is not even idempotent
(measured; the gap channel saturates outright). Storing the encoder's *inputs* is
therefore the only option that replays bit-exactly without touching the core.

The privacy cost of the deviation is paid explicitly by ``PRIVACY_CLAMPS``: raw
facts are clamped to the encoder's own saturation range before storage, so a
stored fact cannot distinguish two inputs the frame would collapse (e.g. a 1-week
and an 11-day gap both pin to 86400). Without that clamp the stored form would
genuinely leak more than the frame — it is not free, it is bought.

Real-history tone exposure (REAL_LOCAL_HISTORY)
-----------------------------------------------
A ``REAL_LOCAL_HISTORY`` export is the ONLY path that writes per-message tone
facts to an off-machine artifact, and it is a real — bounded, disclosed —
*widening* of the runtime privacy surface, NOT a continuation of it. The live
shadow exports nothing, and its production capture (``main.py`` ``capture_request``)
never fills channels 19-26: online those tone channels are ALWAYS invalid. The
channel *indices* match ``v3bridge._DIRECT_CHANNELS`` so the encoder interprets
them identically, but nothing on the live path ever populates them — so this
exporter does not "match an already-accepted online exposure"; it introduces one.

For each real user message the dataset retains, per turn: the lexicon-hit density
of warm/intimacy words (19), cold/dismissive words (20) and distress words (21);
a question flag (22); exclamation and punctuation densities (23, 24); signed
valence (25 = warm − cold); an engagement cue (26); and the privacy-clamped
length (18). From these bounded scalars a key-holder can reconstruct the
per-category hit *counts* and whether a message expressed a warm / cold /
distressed tone — an approximate per-message emotional fingerprint. They do NOT
recover the specific words, word order, or identity (session identity is
HMAC-pseudonymized under a permission-restricted key, kept outside Git/packages).
Anyone authorizing a real export must accept this per-message tone fingerprint.

Two keys, two lifetimes
-----------------------
* the *evaluation-link key* is created once per campaign, kept permission
  restricted outside Git/packages, and retained through G4. It length-frames the
  privacy scope/session identity into a stable ``evaluation_group_ref`` and split
  shared by G1 and G3.
* a *source-digest key* is freshly minted per export, used to key the
  source-corpus/source-record digests, recorded only by its own digest, and
  destroyed at freeze.

Pure stdlib.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from sylanne_alpha.v2core.lexicon import read_signals
from sylanne_alpha.v3core import formula_v1 as formula
from sylanne_alpha.v3core.canonical import canonical_sha256
from sylanne_alpha.v3core.contracts import Action, ComputeProfile, SessionRef, TurnContextClass
from sylanne_alpha.v3core.observation.encoder import encode_observation
from sylanne_alpha.v3core.observation.models import DERIVED_CHANNELS, ObservationFacts, ObservationFrame
from sylanne_alpha.v3core.state.codec import encode_state
from sylanne_alpha.v3core.state.seed import SeedProjector, neutral_seed_frame


# --------------------------------------------------------------------------- #
# Frozen schema
# --------------------------------------------------------------------------- #

DATASET_SCHEMA = "v3_encoded_replay_v1"
RECORD_TYPES = ("episode_header", "turn")
# formula v2 (spec §4.3): the neutral evaluation initial state is recomputed under
# the v2 formula (label_free at its all-prior default) and renamed
# ``neutral_eval_v2``.  The episode seed already frames ``formula_digest``, so a v2
# dataset is cryptographically isolated from any v1 dataset regardless of the id;
# the rename makes that isolation legible in the header/manifest too.
INITIAL_STATE_ID = "neutral_eval_v2"
EVALUATION_PROFILE_ID = "FULL_24_STDP"
SPLITS = ("train", "dev", "test")
CONTROL_IDS = ("learned", "frozen", "random", "zero-lr")

#: The legal action set per context, derived from the frozen formula manifest
#: rather than restated by hand, so it can never drift from the scorer's masks.
LEGAL_ACTIONS_BY_CONTEXT = {
    context: tuple(sorted(priors)) for context, priors in formula.CONTEXT_ACTION_PRIORS.items()
}

#: Provenance is a closed, immutable vocabulary: a free-form provenance string
#: would let an exporter silently relabel real history as synthetic.
PROVENANCE_CLASSES = ("SYNTHETIC_V1", "REAL_LOCAL_HISTORY_V1", "GREY_RUNTIME_V1")

OBSERVATION_DIM = formula.OBSERVATION_DIM
VALUE_CHANNELS = tuple(index for index in range(OBSERVATION_DIM) if index not in DERIVED_CHANNELS)
VALUE_CHANNEL_MASK = sum(1 << index for index in VALUE_CHANNELS)

#: The value channels the offline text projection fills from a single message
#: body via the one canonical v2core lexicon (channels 18-26).  These are the RAW
#: pre-normalization facts, indexed like ``v3bridge._DIRECT_CHANNELS`` so the core
#: encoder interprets them identically.  The index mapping matches the live bridge,
#: but the live path does NOT fill 19-26: production capture (main.py
#: ``capture_request``) leaves every tone field ``None``, so online these are
#: always invalid.  This offline exporter is the ONLY path that writes per-message
#: tone facts into an off-machine artifact -- a real, disclosed widening, not a
#: continuation of the runtime surface.  See the module docstring's
#: "Real-history tone exposure".
OFFLINE_TEXT_CHANNELS = (18, 19, 20, 21, 22, 23, 24, 25, 26)
#: Plus the one structural (non-text) fact the offline path can still assert.
OFFLINE_STRUCTURAL_CHANNELS = (30,)
OFFLINE_FILLABLE_CHANNELS = OFFLINE_TEXT_CHANNELS + OFFLINE_STRUCTURAL_CHANNELS
#: Value channels with NO offline fact -- left invalid on every real-history turn,
#: so a consumer must treat them as neutral.  This includes channel 31
#: (gap_seconds): the label-free reaction signal's gap decayer takes the neutral
#: 1.0 attenuator when 31 is missing (spec 1.3), and body.* facts (0-17) have no
#: text-derived source at all.  Declared in the manifest so the neutral treatment
#: is legible offline rather than inferred.
OFFLINE_UNAVAILABLE_CHANNELS = tuple(
    channel for channel in VALUE_CHANNELS if channel not in OFFLINE_FILLABLE_CHANNELS
)

EPISODE_HEADER_FIELDS = (
    "type",
    "schema",
    "dataset_id",
    "provenance_class",
    "evaluation_group_ref",
    "episode_ref",
    "split",
    "initial_state_id",
    "initial_state_b64",
    "initial_state_digest",
    "pending_credit_censored",
    "evaluation_profile_id",
    "evaluation_profile_digest",
    "gate_manifest_digest",
    "formula_digest",
    "model_digest",
    "episode_seed",
    "row_digest",
)

TURN_FIELDS = (
    "type",
    "episode_ref",
    "episode_turn_index",
    "values",
    "valid_mask",
    "context",
    "actual_action",
    "writer_epoch",
    "local_sequence",
    "credit_adjacency",
    "dropped_gap_count",
    "observed_profile_id",
    "observed_profile_digest",
    # formula v2 (spec §1.4): the three-valued same_sender relation the online path-B
    # settlement consumed (true/false/null).  It participates in state evolution (a
    # false censors the reaction, the length baseline is gated on it), so it must be
    # stored for offline replay to reproduce the settlement bit-for-bit.  It is a
    # boolean relation only -- no identity -- so it does not widen the privacy surface.
    "reaction_same_sender",
    "source_record_digest",
    "row_digest",
)

MANIFEST_FIELDS = (
    "schema",
    "dataset_id",
    "provenance_class",
    "formula_version",
    "formula_digest",
    "model_revision",
    "model_digest",
    "evaluation_profile_id",
    "evaluation_profile_digest",
    "gate_manifest_digest",
    "initial_state_id",
    "initial_state_digest",
    "offline_unavailable_channels",
    "row_count",
    "episode_count",
    "turn_count",
    "source_corpus_digest",
    "episodes_digest",
    "groups_digest",
    "splits_digest",
    "evaluation_link_key_id",
    "evaluation_link_key_digest",
    "source_digest_key_id",
    "source_digest_key_destroyed",
    "destroyed_source_key_digest",
    "exporter_commit",
    "exporter_source_digest",
    "dataset_digest",
)

#: Exact field order of the domain-separated episode-seed framing.
EPISODE_SEED_ORDER = (
    "dataset_id",
    "evaluation_group_ref",
    "episode_ref",
    "gate_manifest_digest",
    "formula_digest",
    "model_digest",
    "profile_digest",
)

_EVAL_SEED_DOMAIN = b"SYL3\x01EVAL\x00"
_EVAL_TURN_SEED_DOMAIN = b"SYL3\x01EVALTURN\x00"
_GROUP_DOMAIN = b"sylanne.v3.evaluation-group.v1\x00"
_SPLIT_DOMAIN = b"sylanne.v3.evaluation-split.v1\x00"
_EPISODE_DOMAIN = b"sylanne.v3.evaluation-episode.v1\x00"
_SOURCE_RECORD_DOMAIN = b"sylanne.v3.source-record.v1\x00"
_SOURCE_CORPUS_DOMAIN = b"sylanne.v3.source-corpus.v1\x00"

EVALUATION_LINK_KEY_BYTES = 32
SOURCE_DIGEST_KEY_BYTES = 32


class DatasetError(ValueError):
    """A dataset/manifest violates the frozen schema or an evaluation invariant."""


class PrivacyViolation(ValueError):
    """A record carries raw content that must never leave the host."""


class ExportRefused(RuntimeError):
    """The exporter refused to run under the requested conditions."""


# --------------------------------------------------------------------------- #
# Canonical framing and digests
# --------------------------------------------------------------------------- #


def framed(value: bytes) -> bytes:
    """Length-frame a component so concatenation can never be ambiguous."""

    if type(value) is not bytes:
        raise TypeError("framed requires bytes")
    if len(value) > 0xFFFFFFFF:
        raise ValueError("component exceeds u32 framing")
    return len(value).to_bytes(4, "big") + value


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def row_digest(row: dict) -> str:
    """Digest a record over every field except the digest itself."""

    payload = {key: value for key, value in row.items() if key != "row_digest"}
    return hashlib.sha256(b"sylanne.v3.row.v1\x00" + _canonical_json(payload)).hexdigest()


def file_digest(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# --------------------------------------------------------------------------- #
# Seed derivation (design 17.2)
# --------------------------------------------------------------------------- #


def _seed_framing(**parts: bytes) -> bytes:
    missing = [name for name in EPISODE_SEED_ORDER if name not in parts]
    if missing:
        raise ValueError(f"episode seed framing is missing {missing}")
    return b"".join(framed(parts[name]) for name in EPISODE_SEED_ORDER)


def episode_seed(**parts: bytes) -> bytes:
    """first128(SHA256(EVAL-domain || framed episode components))."""

    return hashlib.sha256(_EVAL_SEED_DOMAIN + _seed_framing(**parts)).digest()[:16]


def control_episode_seed(*, control_id: str, **parts: bytes) -> bytes:
    """A control appends only its length-framed ID to the same episode framing."""

    if type(control_id) is not str or not control_id:
        raise ValueError("control_id must be a non-empty string")
    payload = _EVAL_SEED_DOMAIN + _seed_framing(**parts) + framed(control_id.encode("utf-8"))
    return hashlib.sha256(payload).digest()[:16]


def evaluation_turn_seed(selected_seed: bytes, episode_turn_index: int) -> bytes:
    """Per-turn randomness; the turn index never mutates the episode/control seed."""

    if type(selected_seed) is not bytes:
        raise TypeError("selected_seed must be bytes")
    if type(episode_turn_index) is not int or episode_turn_index < 0:
        raise ValueError("episode_turn_index must be a non-negative int")
    payload = (
        _EVAL_TURN_SEED_DOMAIN
        + framed(selected_seed)
        + framed(episode_turn_index.to_bytes(8, "big"))
    )
    return hashlib.sha256(payload).digest()[:16]


# --------------------------------------------------------------------------- #
# Keys
# --------------------------------------------------------------------------- #


def _current_user_sid() -> str | None:
    whoami = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "whoami.exe"
    if not whoami.exists():
        return None
    try:
        result = subprocess.run(
            [str(whoami), "/user", "/fo", "csv", "/nh"], capture_output=True, timeout=20
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    text = result.stdout.decode("utf-8", "replace").strip()
    if not text:
        return None
    sid = text.split(",")[-1].strip().strip('"')
    return sid if sid.startswith("S-1-") else None


def _icacls(*args: str) -> tuple[int, str]:
    try:
        result = subprocess.run(["icacls", *args], capture_output=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return 1, ""
    # icacls prints in the console codepage; never parse localized names.
    return result.returncode, result.stdout.decode("utf-8", "replace")


def _acl_sids(path: Path) -> list[str] | None:
    """Return the SID of every ACE on ``path``, or None if the ACL is unreadable.

    ``icacls <path> /save`` emits SDDL, which names principals by raw SID. That is
    both locale-independent and *identity*-bearing. Counting ACEs is not: an ACL
    with exactly one ACE granting Everyone (``S-1-1-0``) full control has a count
    of 1 and is world-writable. This function therefore reads who, not how many.
    """

    path = Path(path).resolve()
    handle, save_path = tempfile.mkstemp(prefix="sylanne-acl-", suffix=".sddl")
    os.close(handle)
    try:
        os.unlink(save_path)  # icacls refuses to overwrite an existing acl file
        code, _ = _icacls(str(path), "/save", save_path, "/c", "/q")
        if code != 0 or not os.path.exists(save_path):
            return None
        # Format (measured): "<name>\r\nD:PAI(A;;FA;;;<sid>)(A;;FA;;;WD)\r\n", UTF-16.
        raw = Path(save_path).read_bytes().decode("utf-16", "replace")
        for line in raw.splitlines():
            if line.startswith("D:"):
                # ACE = (type;flags;rights;object_guid;inherit_guid;sid)
                return re.findall(r"\(A;[^;]*;[^;]*;[^;]*;[^;]*;([^)]+)\)", line)
        return None
    except (OSError, ValueError):
        return None
    finally:
        try:
            os.unlink(save_path)
        except OSError:
            pass


def key_file_is_restricted(path: Path) -> bool:
    """True when only the current user has any access to the key file.

    POSIX uses the mode bits. Windows ignores ``os.chmod`` for anything but the
    read-only flag (measured: mode stays 0o666 after ``chmod(0o600)``), so a mode
    assertion there would be security theater. On Windows every ACE's SID must
    equal the current user's SID; well-known groups such as Everyone (S-1-1-0) or
    Users (S-1-5-32-545) make the key unrestricted no matter how few ACEs exist.
    """

    path = Path(path)
    if not path.exists():
        return False
    if os.name == "nt":
        sid = _current_user_sid()
        if sid is None:
            return False  # cannot prove restriction => not restricted
        sids = _acl_sids(path)
        if not sids:
            return False
        return all(entry.strip().upper() == sid.upper() for entry in sids)
    return (path.stat().st_mode & 0o077) == 0


def restrict_key_file(path: Path) -> None:
    """Restrict a key file to its owner, failing closed if it cannot be proven."""

    path = Path(path)
    if os.name == "nt":
        sid = _current_user_sid()
        if sid is None:
            raise ExportRefused("cannot resolve the current user SID to restrict the key file")
        code, _ = _icacls(str(path), "/inheritance:r", "/grant:r", f"*{sid}:F")
        if code != 0:
            raise ExportRefused("icacls refused to restrict the key file")
    else:
        os.chmod(path, 0o600)
    if not key_file_is_restricted(path):
        raise ExportRefused(f"key file {path} is not permission restricted")


@dataclass(frozen=True, slots=True)
class EvaluationLinkKey:
    """Campaign-scoped HMAC key linking the same privacy scope across G1 and G3."""

    key_id: str
    secret: bytes = field(repr=False)
    synthetic: bool = False

    def __post_init__(self) -> None:
        if type(self.key_id) is not str or not self.key_id:
            raise ValueError("key_id must be a non-empty string")
        if type(self.secret) is not bytes or len(self.secret) < EVALUATION_LINK_KEY_BYTES:
            raise ValueError("evaluation-link secret must be at least 32 bytes")

    @property
    def key_digest(self) -> str:
        return hashlib.sha256(b"sylanne.v3.evaluation-link-key.v1\x00" + self.secret).hexdigest()

    def evaluation_group_ref(self, privacy_scope: str, session_identity: str) -> str:
        payload = b"".join(
            (
                _GROUP_DOMAIN,
                framed(self.key_id.encode("utf-8")),
                framed(privacy_scope.encode("utf-8")),
                framed(session_identity.encode("utf-8")),
            )
        )
        return hmac.new(self.secret, payload, hashlib.sha256).hexdigest()

    def split_for(self, evaluation_group_ref: str) -> str:
        payload = _SPLIT_DOMAIN + framed(bytes.fromhex(evaluation_group_ref))
        digest = hmac.new(self.secret, payload, hashlib.sha256).digest()
        bucket = int.from_bytes(digest[:8], "big") % 100
        if bucket < 60:
            return "train"
        if bucket < 80:
            return "dev"
        return "test"


def create_evaluation_link_key(path: Path, *, key_id: str | None = None) -> EvaluationLinkKey:
    """Mint a fresh, permission-restricted evaluation-link key."""

    path = Path(path)
    if path.exists():
        raise ExportRefused(f"refusing to overwrite an existing evaluation-link key at {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path_would_be_tracked(path):
        raise ExportRefused(
            f"refusing to mint an evaluation-link key at {path}: the path is inside "
            "the repository and is not git-ignored, and neither evaluation key may "
            "ever enter Git or a package"
        )
    secret = secrets.token_bytes(EVALUATION_LINK_KEY_BYTES)
    resolved_id = key_id or f"eval-link-{secrets.token_hex(8)}"
    # Create the file EMPTY, restrict it, and only then write the secret. Windows
    # ignores the POSIX mode passed to os.open, so writing first would leave the
    # secret on disk under inherited ACLs until icacls caught up (TOCTOU).
    os.close(os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600))
    restrict_key_file(path)
    payload = _canonical_json(
        {"key_id": resolved_id, "secret": base64.b64encode(secret).decode("ascii")}
    )
    with open(path, "wb") as stream:
        stream.write(payload)
    # Re-prove the restriction survived the write.
    if not key_file_is_restricted(path):
        raise ExportRefused(f"evaluation-link key {path} lost its restriction while being written")
    return EvaluationLinkKey(key_id=resolved_id, secret=secret)


def load_evaluation_link_key(path: Path) -> EvaluationLinkKey:
    """Load an existing evaluation-link key; loss and loosened permissions fail closed.

    There is deliberately no ``require_restricted=False`` escape hatch: an opt-out
    on a security gate is the gate's failure mode, not a convenience.
    """

    path = Path(path)
    if not path.exists():
        raise ExportRefused(f"evaluation-link key {path} is missing; G4 would be INVALID_DATASET")
    if not key_file_is_restricted(path):
        raise ExportRefused(f"evaluation-link key {path} is not permission restricted")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return EvaluationLinkKey(
            key_id=payload["key_id"], secret=base64.b64decode(payload["secret"], validate=True)
        )
    except (ValueError, KeyError, TypeError) as exc:
        raise ExportRefused(f"evaluation-link key {path} is malformed") from exc


def synthetic_link_key(seed: int) -> EvaluationLinkKey:
    """A deliberately NON-SECRET, deterministic key for synthetic corpora only.

    Synthetic data has nothing to protect, so its grouping key is derived from the
    fixture seed and the tracked fixture stays regenerable. Using it on real
    history is refused: a published key would make the group reference a
    re-identification oracle rather than a privacy device.
    """

    secret = hashlib.sha256(b"sylanne.v3.synthetic-link-key.v1\x00" + str(int(seed)).encode("ascii")).digest()
    return EvaluationLinkKey(key_id=f"synthetic-v1-seed-{int(seed)}", secret=secret, synthetic=True)


# --------------------------------------------------------------------------- #
# Canonical neutral evaluation state
# --------------------------------------------------------------------------- #

NEUTRAL_SESSION_REF = SessionRef(
    key_id=INITIAL_STATE_ID, session_digest=b"\x00" * 32, session_generation=0
)


def neutral_eval_state_bytes() -> bytes:
    """The canonical ``neutral_eval_v2`` state payload, identical for every episode."""

    state = SeedProjector().build_initial_state(
        neutral_seed_frame(),
        session_ref=NEUTRAL_SESSION_REF,
        state_generation_id=INITIAL_STATE_ID,
        source_digest=INITIAL_STATE_ID,
    )
    return encode_state(state)


def neutral_eval_state_digest() -> str:
    return hashlib.sha256(neutral_eval_state_bytes()).hexdigest()


def encode_state_bytes(state) -> bytes:
    """Canonical persistence bytes of a state, for byte-identity assertions."""

    return encode_state(state)


def evaluation_profile() -> ComputeProfile:
    snn_enabled, ticks, stdp_enabled, reuse = formula.COMPUTE_PROFILES[EVALUATION_PROFILE_ID]
    return ComputeProfile(
        profile_id=EVALUATION_PROFILE_ID,
        snn_enabled=snn_enabled,
        ticks=ticks,
        stdp_enabled=stdp_enabled,
        reuse_last_summary=reuse,
        math_backend="scalar-v1",
        formula_version=formula.FORMULA_VERSION,
        model_version=formula.FORMULA_VERSION,
    )


def evaluation_profile_digest() -> str:
    return canonical_sha256(evaluation_profile())


# --------------------------------------------------------------------------- #
# Privacy projection
# --------------------------------------------------------------------------- #

#: Single *tokens* that can only ever belong to raw content or a raw identifier.
#: Keys are split on non-alphanumerics before matching, so ``session_id`` must be
#: listed as ``session``/``id`` rather than as the joined phrase — a phrase like
#: "session_id" would never match a tokenized key.
_RAW_FIELD_MARKERS = (
    "text", "content", "message", "messages", "prompt", "reply", "replies",
    "completion", "history", "session", "user", "sender", "origin", "persona",
    "memory", "path", "title", "nickname", "platform", "cid", "conversation",
    "secret", "token", "password", "key", "raw", "id", "uid", "name", "nick",
)

_SECRET_MARKERS = (b"BEGIN PRIVATE KEY", b"BEGIN RSA", b"api_key", b"password", b"Bearer ")

#: The closed tagged schema. Anything outside it is guilty until proven innocent.
_DECLARED_FIELDS = frozenset(EPISODE_HEADER_FIELDS + TURN_FIELDS)

#: The only field allowed to be long: the canonical neutral initial-state payload,
#: which is machine-generated core bytes rather than host content.
_LONG_VALUE_ALLOWED = frozenset({"initial_state_b64"})


def assert_no_raw_content(record: dict) -> None:
    """Refuse any record carrying a raw-content or raw-identifier field.

    Field names are matched on whole tokens, not substrings: naive substring
    matching flags the declared ``context`` channel because it contains
    ``content``.
    """

    for key, value in record.items():
        if key not in _DECLARED_FIELDS:
            tokens = set(re.split(r"[^a-z0-9]+", key.lower()))
            if tokens & set(_RAW_FIELD_MARKERS):
                raise PrivacyViolation(f"record field {key!r} may carry raw content")
        if isinstance(value, str) and len(value) > 256 and key not in _LONG_VALUE_ALLOWED:
            raise PrivacyViolation(f"record field {key!r} carries an over-long raw string")
    blob = _canonical_json(record)
    for marker in _SECRET_MARKERS:
        if marker in blob:
            raise PrivacyViolation("record carries a secret marker")


def _mint_source_key() -> bytearray:
    """A fresh per-export source-digest key held in mutable memory so it can be wiped."""

    return bytearray(secrets.token_bytes(SOURCE_DIGEST_KEY_BYTES))


def destroy_source_key(source_key: bytearray) -> None:
    """Overwrite the source-digest key in place at freeze.

    Rebinding an immutable ``bytes`` (``key = b"\\x00" * len(key)``) only drops the
    reference and leaves the secret in freed heap, so the key must live in a
    ``bytearray`` and be overwritten element-wise. This is best effort and stated
    as such: CPython may still hold transient copies (HMAC internals, the original
    ``token_bytes`` result), and Python cannot guarantee erasure of every copy. The
    manifest therefore claims only that this exporter destroyed its own reference
    and records the key's digest, never the key.
    """

    if type(source_key) is not bytearray:
        raise TypeError("only a bytearray source key can be destroyed in place")
    for index in range(len(source_key)):
        source_key[index] = 0


def source_record_digest(source_key: bytes, *components: str) -> str:
    payload = _SOURCE_RECORD_DOMAIN + b"".join(framed(part.encode("utf-8")) for part in components)
    return hmac.new(source_key, payload, hashlib.sha256).hexdigest()


def source_corpus_digest(source_key: bytes, corpus: bytes) -> str:
    payload = _SOURCE_CORPUS_DOMAIN + framed(corpus)
    return hmac.new(source_key, payload, hashlib.sha256).hexdigest()


def episode_ref_for(source_key: bytes, evaluation_group_ref: str, ordinal: int) -> str:
    payload = (
        _EPISODE_DOMAIN
        + framed(bytes.fromhex(evaluation_group_ref))
        + framed(int(ordinal).to_bytes(8, "big"))
    )
    return hmac.new(source_key, payload, hashlib.sha256).hexdigest()


# --------------------------------------------------------------------------- #
# Frames
# --------------------------------------------------------------------------- #


#: Saturation clamps applied at EXPORT so a stored fact can never carry more
#: information than the encoder's own output would. Channel 31 (gap) saturates at
#: 86400 s inside the encoder; storing the unclamped value would keep 1 day, 1
#: week and 11 days distinct where the frame collapses all three to one value.
#: Channels 13/18 (lengths) are clamped to the tanh-saturation knee for the same
#: reason: an exact character count is a strong linkage fingerprint.
PRIVACY_CLAMPS = {31: (0.0, 86400.0), 13: (0.0, 4096.0), 18: (0.0, 4096.0)}


def privacy_clamp(channel: int, value: float) -> float:
    """Clamp a raw fact to the encoder's own saturation range before storing."""

    bounds = PRIVACY_CLAMPS.get(channel)
    if bounds is None:
        return float(value)
    low, high = bounds
    return float(low if value < low else high if value > high else value)


def frame_for_turn(turn: dict, previous_action: Action | None = None) -> ObservationFrame:
    """Rebuild the exact observation frame the core will see for a stored turn."""

    values = turn["values"]
    mask = turn["valid_mask"]
    raw: list[float | None] = []
    for index in range(OBSERVATION_DIM):
        if index in DERIVED_CHANNELS or not (mask >> index) & 1:
            raw.append(None)
        else:
            raw.append(float(values[index]))
    facts = ObservationFacts(
        raw_values=tuple(raw),
        context=TurnContextClass(turn["context"]),
        previous_action=previous_action,
    )
    return encode_observation(facts)


# --------------------------------------------------------------------------- #
# Dataset DTOs and reader
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class Episode:
    header: dict
    turns: tuple

    @property
    def episode_ref(self) -> str:
        return self.header["episode_ref"]

    @property
    def evaluation_group_ref(self) -> str:
        return self.header["evaluation_group_ref"]

    @property
    def split(self) -> str:
        return self.header["split"]

    @property
    def episode_seed(self) -> bytes:
        return bytes.fromhex(self.header["episode_seed"])


@dataclass(frozen=True, slots=True)
class Dataset:
    episodes: tuple
    row_count: int

    @property
    def episode_count(self) -> int:
        return len(self.episodes)

    def split_episodes(self, split: str) -> tuple:
        return tuple(episode for episode in self.episodes if episode.split == split)


def validate_row(row: dict) -> None:
    """Structural + digest validation of a single tagged record."""

    if not isinstance(row, dict) or "type" not in row:
        raise DatasetError("every record must be an object with a declared type")
    kind = row["type"]
    if kind not in RECORD_TYPES:
        raise DatasetError(f"record type {kind!r} is outside the tagged schema")
    expected = EPISODE_HEADER_FIELDS if kind == "episode_header" else TURN_FIELDS
    if set(row) != set(expected):
        unexpected = sorted(set(row) - set(expected))
        missing = sorted(set(expected) - set(row))
        raise DatasetError(
            f"{kind} record has fields outside the tagged schema (extra={unexpected}, missing={missing})"
        )
    if row["row_digest"] != row_digest(row):
        raise DatasetError(f"{kind} row_digest does not match its content")
    assert_no_raw_content({k: v for k, v in row.items() if k not in ("source_record_digest", "row_digest")})

    if kind == "episode_header":
        _validate_header(row)
    else:
        _validate_turn(row)


def _validate_header(row: dict) -> None:
    if row["schema"] != DATASET_SCHEMA:
        raise DatasetError("episode header declares an unknown schema")
    if row["provenance_class"] not in PROVENANCE_CLASSES:
        raise DatasetError(f"provenance class {row['provenance_class']!r} is not declared/immutable")
    if row["split"] not in SPLITS:
        raise DatasetError(f"split {row['split']!r} is not declared")
    if row["initial_state_id"] != INITIAL_STATE_ID:
        raise DatasetError(f"episode header must carry the {INITIAL_STATE_ID} initial_state")
    payload = row["initial_state_b64"].encode("ascii")
    if hashlib.sha256(payload).hexdigest() != row["initial_state_digest"]:
        raise DatasetError("episode header initial_state_digest does not match its bytes")
    if row["initial_state_digest"] != neutral_eval_state_digest():
        raise DatasetError(f"episode header initial_state is not the canonical {INITIAL_STATE_ID} state")
    if row["pending_credit_censored"] is not True:
        raise DatasetError("episode boundary credit must be censored")
    if row["evaluation_profile_id"] != EVALUATION_PROFILE_ID:
        raise DatasetError("episode header must fix the FULL_24_STDP evaluation profile")
    if len(bytes.fromhex(row["episode_seed"])) != 16:
        raise DatasetError("episode_seed must be 128 bits")
    # The manifest declares the derivation; enforce it at read time too, or a
    # hand-edited (re-signed) header could pin an attacker-chosen seed.
    expected = episode_seed(
        dataset_id=bytes.fromhex(row["dataset_id"]),
        evaluation_group_ref=bytes.fromhex(row["evaluation_group_ref"]),
        episode_ref=bytes.fromhex(row["episode_ref"]),
        gate_manifest_digest=bytes.fromhex(row["gate_manifest_digest"]),
        formula_digest=bytes.fromhex(row["formula_digest"]),
        model_digest=bytes.fromhex(row["model_digest"]),
        profile_digest=bytes.fromhex(row["evaluation_profile_digest"]),
    )
    if bytes.fromhex(row["episode_seed"]) != expected:
        raise DatasetError("episode_seed is not the declared domain-separated derivation")


def _validate_turn(row: dict) -> None:
    values = row["values"]
    if not isinstance(values, list) or len(values) != OBSERVATION_DIM:
        raise DatasetError("a turn must carry exactly 36 values")
    for value in values:
        if not isinstance(value, float) or value != value or value in (float("inf"), float("-inf")):
            raise DatasetError("turn values must be finite floats")
    mask = row["valid_mask"]
    if not isinstance(mask, int) or not 0 <= mask < (1 << OBSERVATION_DIM):
        raise DatasetError("valid_mask must be a 36-bit mask")
    if mask & ~VALUE_CHANNEL_MASK:
        raise DatasetError("derived observation channels must never be stored as facts")
    for channel in range(OBSERVATION_DIM):
        if not (mask >> channel) & 1 and values[channel] != 0.0:
            # An ignored-but-nonzero slot is a covert channel: replay never reads it
            # and no privacy scan inspects it.
            raise DatasetError(
                f"channel {channel} is masked off and must be stored as 0.0, not {values[channel]!r}"
            )
    if row["context"] not in tuple(item.value for item in TurnContextClass):
        raise DatasetError("turn context is not a declared TurnContextClass")
    if row["actual_action"] not in tuple(item.value for item in Action) + ("UNKNOWN",):
        raise DatasetError("actual_action must be a declared Action or UNKNOWN")
    if not isinstance(row["credit_adjacency"], bool):
        raise DatasetError("credit_adjacency must be a bool")
    if not isinstance(row["dropped_gap_count"], int) or row["dropped_gap_count"] < 0:
        raise DatasetError("dropped_gap_count must be a non-negative int")
    # An adjacent credit claim and an admitted gap are mutually exclusive: any gap
    # censors delayed credit, so claiming both is an ambiguous gap.
    if row["credit_adjacency"] and row["dropped_gap_count"] != 0:
        raise DatasetError("ambiguous gap: credit_adjacency cannot hold across a dropped gap")
    # The same_sender relation is strictly three-valued (spec §1.4).  A plain int must
    # be rejected even though ``1 == True``: ``isinstance(1, bool)`` is False, so the
    # exact-type test keeps a stray integer (a covert channel) out.
    same_sender = row["reaction_same_sender"]
    if same_sender is not None and not isinstance(same_sender, bool):
        raise DatasetError("reaction_same_sender must be true, false, or null")
    if len(bytes.fromhex(row["source_record_digest"])) != 32:
        raise DatasetError("source_record_digest must be a keyed 256-bit digest")


def read_dataset(path: Path) -> Dataset:
    """Parse, validate, and group an encoded dataset into episodes."""

    path = Path(path)
    rows = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError as exc:
            raise DatasetError(f"line {number} is not valid JSON") from exc
        validate_row(row)
        rows.append(row)
    if not rows:
        raise DatasetError("dataset is empty")

    headers: dict[str, dict] = {}
    turns: dict[str, list] = {}
    order: list[str] = []
    for row in rows:
        if row["type"] == "episode_header":
            ref = row["episode_ref"]
            if ref in headers:
                raise DatasetError(f"duplicate episode header for {ref}")
            headers[ref] = row
            turns[ref] = []
            order.append(ref)
        else:
            ref = row["episode_ref"]
            if ref not in headers:
                raise DatasetError(f"turn precedes its episode header for {ref}")
            turns[ref].append(row)

    # An evaluation group may contribute many episodes but can never cross a split.
    group_splits: dict[str, str] = {}
    dataset_ids = set()
    for ref in order:
        header = headers[ref]
        dataset_ids.add(header["dataset_id"])
        group = header["evaluation_group_ref"]
        split = header["split"]
        if group in group_splits and group_splits[group] != split:
            raise DatasetError(
                f"evaluation group {group[:12]}... crosses a split "
                f"({group_splits[group]} and {split})"
            )
        group_splits[group] = split
    if len(dataset_ids) != 1:
        raise DatasetError("a dataset file must carry exactly one dataset_id")

    episodes = []
    for ref in order:
        rows_for_episode = sorted(turns[ref], key=lambda row: row["episode_turn_index"])
        for position, turn in enumerate(rows_for_episode):
            if turn["episode_turn_index"] != position:
                raise DatasetError(f"episode {ref[:12]}... has a non-contiguous turn index")
        if rows_for_episode and rows_for_episode[0]["credit_adjacency"]:
            raise DatasetError("the first turn of an episode cannot claim adjacent credit")
        episodes.append(Episode(header=headers[ref], turns=tuple(rows_for_episode)))
    return Dataset(episodes=tuple(episodes), row_count=len(rows))


def _validate_offline_unavailable_channels(channels: object) -> tuple[int, ...]:
    """Coerce/validate the offline-unavailable channel declaration.

    The list names value channels the offline projection could not fill and left
    invalid on every turn (see ``OFFLINE_UNAVAILABLE_CHANNELS``).  It must be a
    canonical, sorted, unique list of *value* channels: a derived channel is always
    computed and can never be 'unavailable', and a duplicate/unsorted list would
    make the manifest non-canonical.  Booleans are rejected explicitly because
    ``bool`` is an ``int`` subclass and would otherwise smuggle a covert flag.
    """

    if not isinstance(channels, (list, tuple)):
        raise DatasetError("offline_unavailable_channels must be a list of channel indices")
    result: list[int] = []
    for channel in channels:
        if type(channel) is not int:
            raise DatasetError("offline_unavailable_channels must contain plain ints")
        if channel not in VALUE_CHANNELS:
            raise DatasetError(
                f"offline_unavailable_channels entry {channel} is not a value channel"
            )
        result.append(channel)
    if result != sorted(result) or len(set(result)) != len(result):
        raise DatasetError("offline_unavailable_channels must be sorted and unique")
    return tuple(result)


def validate_manifest(manifest: dict) -> None:
    missing = [name for name in MANIFEST_FIELDS if name not in manifest]
    if missing:
        raise DatasetError(f"manifest is missing {missing}")
    if manifest["schema"] != DATASET_SCHEMA:
        raise DatasetError("manifest declares an unknown schema")
    _validate_offline_unavailable_channels(manifest["offline_unavailable_channels"])
    if manifest["provenance_class"] not in PROVENANCE_CLASSES:
        raise DatasetError(
            f"provenance class {manifest['provenance_class']!r} is not declared/immutable"
        )
    if manifest["evaluation_profile_id"] != EVALUATION_PROFILE_ID:
        raise DatasetError("manifest must fix the FULL_24_STDP evaluation profile")
    if manifest["initial_state_id"] != INITIAL_STATE_ID:
        raise DatasetError(f"manifest must fix the {INITIAL_STATE_ID} initial state")
    if manifest["source_digest_key_destroyed"] is not True:
        raise DatasetError("the per-export source-digest key must be destroyed at freeze")
    if manifest["formula_digest"] != formula.FORMULA_DIGEST:
        raise DatasetError("manifest formula digest does not match this build")


def load_dataset_with_manifest(path: Path, manifest: dict) -> Dataset:
    validate_manifest(manifest)
    dataset = read_dataset(path)
    actual = file_digest(path)
    if actual != manifest["dataset_digest"]:
        raise DatasetError("dataset_digest does not match the dataset bytes")
    if dataset.row_count != manifest["row_count"]:
        raise DatasetError("manifest row_count does not match the dataset")
    # Honesty gate: a channel the manifest declares offline-unavailable must be
    # invalid in EVERY turn.  A manifest that claims a filled channel is neutral
    # would mislead the label-free consumer into ignoring a real signal.
    declared = _validate_offline_unavailable_channels(manifest["offline_unavailable_channels"])
    if declared:
        for episode in dataset.episodes:
            for turn in episode.turns:
                for channel in declared:
                    if (turn["valid_mask"] >> channel) & 1:
                        raise DatasetError(
                            f"manifest declares channel {channel} offline-unavailable "
                            "but a turn fills it"
                        )
    return dataset


# --------------------------------------------------------------------------- #
# Git / provenance helpers
# --------------------------------------------------------------------------- #


def _git(*args: str) -> tuple[int, str]:
    try:
        result = subprocess.run(
            ["git", "-c", f"safe.directory={_REPO_ROOT}", *args],
            capture_output=True,
            cwd=str(_REPO_ROOT),
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return 1, ""
    return result.returncode, result.stdout.decode("utf-8", "replace")


def path_is_git_ignored(path: Path) -> bool:
    """True when Git would refuse to track the path (keys/evidence must be ignored)."""

    code, _ = _git("check-ignore", "-q", str(path))
    return code == 0


def path_would_be_tracked(path: Path) -> bool:
    """True when Git could track this path: inside the repo and not ignored.

    A key outside the working tree is fine — ``git check-ignore`` simply has no
    opinion about it, so 'not ignored' must not be read as 'would be committed'.
    """

    resolved = Path(path).resolve()
    try:
        resolved.relative_to(_REPO_ROOT)
    except ValueError:
        return False  # outside the repository entirely
    return not path_is_git_ignored(resolved)


def exporter_commit() -> str:
    """The commit whose source produced a dataset, honestly marked when dirty.

    Returns HEAD when this exporter's own source is committed, so a consumer can
    trust HEAD names the exact source that ran.  When the exporter source has
    uncommitted changes no commit truthfully names it -- a fixture regenerated in
    the same commit that edits the exporter cannot embed that commit's own hash --
    so we append ``-dirty`` rather than assert a commit whose tracked source differs
    from what actually ran.  Real exports (``export_real_history``) enforce a clean
    tracked tree first, so they always get a bare hash; only synthetic dev fixtures
    regenerated from a dirty tree carry the marker.  ``exporter_source_digest`` is
    the authoritative, commit-independent lineage in every case.
    """

    code, out = _git("rev-parse", "HEAD")
    if code != 0:
        return "UNKNOWN"
    head = out.strip()
    status_code, status = _git("status", "--porcelain", "--", str(Path(__file__).resolve()))
    if status_code == 0 and status.strip():
        return f"{head}-dirty"
    return head


def exporter_source_digest() -> str:
    """Canonical digest of this exporter's own source."""

    return hashlib.sha256(Path(__file__).resolve().read_bytes()).hexdigest()


def tracked_tree_is_clean() -> bool:
    code, out = _git("status", "--porcelain", "--untracked-files=no")
    return code == 0 and not out.strip()


def resolve_data_dir(value: object) -> Path:
    """Only an explicitly supplied data directory may ever be read."""

    if value is None or value == "":
        raise ExportRefused(
            "refusing to guess a history location: --astrbot-data-dir must be explicit"
        )
    path = Path(str(value)).expanduser()
    if not path.is_dir():
        raise ExportRefused(f"supplied data directory {path} does not exist")
    return path


# --------------------------------------------------------------------------- #
# Export core
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class SourceTurn:
    """One already-privacy-projected source turn (no text, no identifiers)."""

    values: tuple
    valid_mask: int
    context: str
    actual_action: str
    writer_epoch: int
    local_sequence: int
    dropped_gap_count: int
    #: The three-valued same_sender relation (spec §1.4).  ``None`` = the source could
    #: not decide (offline synthetic groups may leave it null as declared noise).
    reaction_same_sender: bool | None = None
    observed_profile_id: str | None = None
    observed_profile_digest: str | None = None
    source_components: tuple = ()


@dataclass(frozen=True, slots=True)
class SourceEpisode:
    privacy_scope: str
    session_identity: str
    ordinal: int
    turns: tuple


@dataclass(frozen=True, slots=True)
class ExportResult:
    output: Path
    manifest_path: Path
    manifest: dict
    source_corpus_bytes: bytes
    source_identifiers: tuple
    source_key_material: bytes | None


def _build_records(
    episodes: Sequence[SourceEpisode],
    *,
    link_key: EvaluationLinkKey,
    source_key: bytes,
    dataset_id: bytes,
    provenance_class: str,
    gate_manifest_digest: str,
) -> list[dict]:
    state_bytes = neutral_eval_state_bytes()
    state_b64 = state_bytes.decode("ascii")
    state_digest = hashlib.sha256(state_bytes).hexdigest()
    profile_digest = evaluation_profile_digest()
    rows: list[dict] = []

    for episode in episodes:
        group_ref = link_key.evaluation_group_ref(episode.privacy_scope, episode.session_identity)
        split = link_key.split_for(group_ref)
        episode_ref = episode_ref_for(source_key, group_ref, episode.ordinal)
        seed = episode_seed(
            dataset_id=dataset_id,
            evaluation_group_ref=bytes.fromhex(group_ref),
            episode_ref=bytes.fromhex(episode_ref),
            gate_manifest_digest=bytes.fromhex(gate_manifest_digest),
            formula_digest=bytes.fromhex(formula.FORMULA_DIGEST),
            model_digest=bytes.fromhex(formula.FORMULA_DIGEST),
            profile_digest=bytes.fromhex(profile_digest),
        )
        header = {
            "type": "episode_header",
            "schema": DATASET_SCHEMA,
            "dataset_id": dataset_id.hex(),
            "provenance_class": provenance_class,
            "evaluation_group_ref": group_ref,
            "episode_ref": episode_ref,
            "split": split,
            "initial_state_id": INITIAL_STATE_ID,
            "initial_state_b64": state_b64,
            "initial_state_digest": state_digest,
            "pending_credit_censored": True,
            "evaluation_profile_id": EVALUATION_PROFILE_ID,
            "evaluation_profile_digest": profile_digest,
            "gate_manifest_digest": gate_manifest_digest,
            "formula_digest": formula.FORMULA_DIGEST,
            "model_digest": formula.FORMULA_DIGEST,
            "episode_seed": seed.hex(),
        }
        header["row_digest"] = row_digest(header)
        rows.append(header)

        for index, turn in enumerate(episode.turns):
            # Episode boundaries censor credit; so does any dropped/unmatched gap.
            adjacency = index > 0 and turn.dropped_gap_count == 0
            row = {
                "type": "turn",
                "episode_ref": episode_ref,
                "episode_turn_index": index,
                "values": [
                    privacy_clamp(channel, value) if (turn.valid_mask >> channel) & 1 else 0.0
                    for channel, value in enumerate(turn.values)
                ],
                "valid_mask": int(turn.valid_mask),
                "context": turn.context,
                "actual_action": turn.actual_action,
                "writer_epoch": int(turn.writer_epoch),
                "local_sequence": int(turn.local_sequence),
                "credit_adjacency": bool(adjacency),
                "dropped_gap_count": int(turn.dropped_gap_count),
                "observed_profile_id": turn.observed_profile_id,
                "observed_profile_digest": turn.observed_profile_digest,
                "reaction_same_sender": turn.reaction_same_sender,
                "source_record_digest": source_record_digest(
                    source_key, episode_ref, str(index), *turn.source_components
                ),
            }
            row["row_digest"] = row_digest(row)
            rows.append(row)
    return rows


def _write_export(
    rows: list[dict],
    *,
    output: Path,
    manifest_path: Path,
    link_key: EvaluationLinkKey,
    source_key: bytes,
    source_key_id: str,
    dataset_id: bytes,
    provenance_class: str,
    gate_manifest_digest: str,
    source_corpus: bytes,
    offline_unavailable_channels: Sequence[int] = (),
) -> dict:
    output = Path(output)
    manifest_path = Path(manifest_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    for row in rows:
        validate_row(row)

    unavailable = _validate_offline_unavailable_channels(list(offline_unavailable_channels))
    # Never emit a manifest that lies: a channel declared offline-unavailable must
    # be invalid in every turn we are about to write.
    for row in rows:
        if row["type"] != "turn":
            continue
        for channel in unavailable:
            if (row["valid_mask"] >> channel) & 1:
                raise DatasetError(
                    f"declared offline-unavailable channel {channel} is filled by a turn"
                )

    body = "\n".join(json.dumps(row, sort_keys=True, ensure_ascii=False) for row in rows) + "\n"
    output.write_text(body, encoding="utf-8")

    headers = [row for row in rows if row["type"] == "episode_header"]
    turns = [row for row in rows if row["type"] == "turn"]
    manifest = {
        "schema": DATASET_SCHEMA,
        "dataset_id": dataset_id.hex(),
        "provenance_class": provenance_class,
        "formula_version": formula.FORMULA_VERSION,
        "formula_digest": formula.FORMULA_DIGEST,
        "model_revision": formula.ACTION_MODEL_REVISION,
        "model_digest": formula.FORMULA_DIGEST,
        "evaluation_profile_id": EVALUATION_PROFILE_ID,
        "evaluation_profile_digest": evaluation_profile_digest(),
        "gate_manifest_digest": gate_manifest_digest,
        "initial_state_id": INITIAL_STATE_ID,
        "initial_state_digest": neutral_eval_state_digest(),
        "offline_unavailable_channels": list(unavailable),
        "row_count": len(rows),
        "episode_count": len(headers),
        "turn_count": len(turns),
        "source_corpus_digest": source_corpus_digest(source_key, source_corpus),
        "episodes_digest": hashlib.sha256(
            b"".join(framed(bytes.fromhex(row["episode_ref"])) for row in headers)
        ).hexdigest(),
        "groups_digest": hashlib.sha256(
            b"".join(framed(bytes.fromhex(row["evaluation_group_ref"])) for row in headers)
        ).hexdigest(),
        "splits_digest": hashlib.sha256(
            b"".join(framed(row["split"].encode("ascii")) for row in headers)
        ).hexdigest(),
        "evaluation_link_key_id": link_key.key_id,
        "evaluation_link_key_digest": link_key.key_digest,
        "source_digest_key_id": source_key_id,
        "source_digest_key_destroyed": True,
        "destroyed_source_key_digest": hashlib.sha256(
            b"sylanne.v3.source-digest-key.v1\x00" + source_key
        ).hexdigest(),
        "exporter_commit": exporter_commit(),
        "exporter_source_digest": exporter_source_digest(),
        "dataset_digest": file_digest(output),
    }
    validate_manifest(manifest)
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def default_gate_manifest_digest() -> str:
    return file_digest(_REPO_ROOT / "tests" / "fixtures" / "v3_gate_manifest_v1.json")


# --------------------------------------------------------------------------- #
# Synthetic corpus
# --------------------------------------------------------------------------- #


def _synthetic_turns(rng, count: int) -> tuple:
    """Build synthetic, already-normalized channel facts."""

    turns = []
    epoch = 1
    sequence = 0
    for index in range(count):
        values = [0.0] * OBSERVATION_DIM
        mask = 0
        for channel in VALUE_CHANNELS:
            if rng.random() < 0.12:
                continue  # a genuinely missing fact stays invalid
            if channel in (22, 30):
                value = float(rng.randint(0, 1))
            elif channel == 31:
                value = float(rng.randint(0, 90_000))
            elif channel in (13, 18):
                value = float(rng.randint(0, 400))
            elif channel in (0, 11, 12):
                value = rng.uniform(-1.0, 1.0)
            elif channel in (7, 8, 10, 14, 15, 17):
                value = rng.uniform(0.0, 3.0)
            elif channel == 25:
                value = rng.uniform(-3.0, 3.0)
            else:
                value = rng.random()
            values[channel] = float(value)
            mask |= 1 << channel
        # The actual action must be legal for its context. The policy scores a
        # legal-only softmax, so an out-of-context label would carry probability
        # zero and saturate log loss at -log(eps) — a meaningless metric rather
        # than a hard one. Context weights are skewed towards PROACTIVE so REACH
        # clears the >=30-known-examples-per-action coverage gate.
        context = rng.choices(
            ["ADDRESSED", "AMBIENT", "PROACTIVE", "IDLE"], weights=[0.40, 0.20, 0.30, 0.10]
        )[0]
        if rng.random() < 0.10:
            action = "UNKNOWN"  # no structured terminal receipt: credit is censored
        else:
            action = rng.choice(LEGAL_ACTIONS_BY_CONTEXT[context])
        gap = 0 if rng.random() < 0.85 else rng.randint(1, 3)
        # The sequence must actually skip the dropped turns, otherwise the core's
        # own adjacency test (local_sequence == previous + 1) would silently settle
        # credit across a gap that the dataset declares non-adjacent.
        sequence += 1 + gap
        # A three-valued same_sender relation (spec §1.4): mostly the same conversant
        # replied, with a minority of interjections (False, censors the reaction) and
        # undecided cases (None, admitted noise), so replay exercises all three.
        same_sender = rng.choices([True, False, None], weights=[0.80, 0.12, 0.08])[0]
        turns.append(
            SourceTurn(
                values=tuple(values),
                valid_mask=mask,
                context=context,
                actual_action=action,
                writer_epoch=epoch,
                local_sequence=sequence,
                dropped_gap_count=gap,
                reaction_same_sender=same_sender,
                source_components=(f"synthetic-record-{index}",),
            )
        )
    return tuple(turns)


def export_synthetic(
    *,
    output: Path,
    manifest_path: Path,
    link_key: EvaluationLinkKey,
    seed: int = 2718,
    groups: int = 24,
    episodes_per_group: int = 1,
    turns_per_episode: int = 12,
    gate_manifest_digest: str | None = None,
) -> ExportResult:
    """Export a fully synthetic, traceable corpus (never touches real history)."""

    import random

    rng = random.Random(seed)
    identifiers = []
    episodes = []
    for group_index in range(groups):
        # A traceable synthetic identity; it must never reach the encoded dataset.
        identity = f"synthetic-session-{seed}-{group_index:04d}"
        identifiers.append(identity)
        for ordinal in range(episodes_per_group):
            episodes.append(
                SourceEpisode(
                    privacy_scope="SYNTHETIC",
                    session_identity=identity,
                    ordinal=ordinal,
                    turns=_synthetic_turns(rng, turns_per_episode),
                )
            )

    source_corpus = _canonical_json(
        {"seed": seed, "identities": identifiers, "turns_per_episode": turns_per_episode}
    )
    source_key = _mint_source_key()
    source_key_id = f"source-{secrets.token_hex(8)}"
    dataset_id = secrets.token_bytes(16)
    digest = gate_manifest_digest or default_gate_manifest_digest()

    rows = _build_records(
        episodes,
        link_key=link_key,
        source_key=source_key,
        dataset_id=dataset_id,
        provenance_class="SYNTHETIC_V1",
        gate_manifest_digest=digest,
    )
    manifest = _write_export(
        rows,
        output=Path(output),
        manifest_path=Path(manifest_path),
        link_key=link_key,
        source_key=source_key,
        source_key_id=source_key_id,
        dataset_id=dataset_id,
        provenance_class="SYNTHETIC_V1",
        gate_manifest_digest=digest,
        source_corpus=source_corpus,
    )
    # Destroy the per-export source-digest key in place: only its digest survives.
    destroy_source_key(source_key)
    return ExportResult(
        output=Path(output),
        manifest_path=Path(manifest_path),
        manifest=manifest,
        source_corpus_bytes=source_corpus,
        source_identifiers=tuple(identifiers),
        source_key_material=None,
    )


# --------------------------------------------------------------------------- #
# Real local history (explicit data directory only)
# --------------------------------------------------------------------------- #


def read_local_history(data_dir: Path) -> tuple[list[SourceEpisode], bytes, tuple]:
    """Project AstrBot's local conversation history into privacy-safe source turns.

    Grounded in the installed AstrBot v4 schema: ``<data_dir>/data_v4.db`` holds a
    ``conversations`` table whose ``content`` column is a JSON list of
    OpenAI-format messages. The database is opened read-only, and only *derived
    numeric facts* ever leave this function: no text, no identifiers, no titles.
    """

    data_dir = resolve_data_dir(data_dir)
    db_path = data_dir / "data_v4.db"
    if not db_path.exists():
        raise ExportRefused(f"no AstrBot v4 database at {db_path}")

    connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            "SELECT conversation_id, platform_id, user_id, content, updated_at "
            "FROM conversations ORDER BY updated_at ASC"
        ).fetchall()
    except sqlite3.Error as exc:
        raise ExportRefused(f"cannot read conversations from {db_path}: {exc}") from exc
    finally:
        connection.close()

    episodes: list[SourceEpisode] = []
    corpus_parts: list[bytes] = []
    for ordinal, record in enumerate(rows):
        try:
            messages = json.loads(record["content"] or "[]")
        except ValueError:
            continue
        if not isinstance(messages, list) or not messages:
            continue
        # The corpus digest is keyed later; only stable structural facts feed it.
        corpus_parts.append(
            framed(f"{record['conversation_id']}:{len(messages)}:{record['updated_at']}".encode("utf-8"))
        )
        turns = _project_messages(messages)
        if not turns:
            continue
        episodes.append(
            SourceEpisode(
                privacy_scope="LOCAL_HISTORY",
                session_identity=f"{record['platform_id']}\x00{record['user_id']}",
                ordinal=ordinal,
                turns=turns,
            )
        )
    return episodes, b"".join(corpus_parts), tuple()


def _lexicon_channel_facts(content: object) -> dict[int, float]:
    """Project one message body into RAW facts for text channels 18-26.

    Reads the body once through the single canonical v2core lexicon and returns the
    RAW pre-normalization facts (densities, a question flag, a length count).  The
    text is read once and immediately discarded; only the aggregate bounded scalars
    leave.

    Privacy: this is the ONLY path that writes per-message tone facts into an
    off-machine artifact.  The live shadow does not -- production capture
    (``main.py`` ``capture_request``) never fills channels 19-26, so online they are
    always invalid.  See the module docstring's "Real-history tone exposure".

    The length-normalized densities (19-21, 23-25) are re-normalized to the
    privacy-CLAMPED length, not the true length: channel 18 saturates at 4096, and
    ``read_signals`` divides counts by the *true* length, so a >4096-char body would
    otherwise leak its true length back through the density denominator and defeat
    channel 18's fingerprint clamp.  For a body within the clamp we store the raw
    lexicon read verbatim (a byte-exact no-op).  Only for a >4096-char body do we
    recover the integer hit COUNTS and recompute ``count * 10 / clamped_length`` --
    recomputing from the count (not rescaling the already-divided density) makes the
    result bit-invariant to the true length, so its low-order float bits cannot leak
    it either.  ``engagement_cue`` (26) already saturates at length>=40 so it carries
    no length past the clamp.

    Absent or empty text yields an empty mapping: the tone channels then stay
    INVALID rather than carry a fabricated zero-density observation.  A non-empty
    body with no lexicon hits still returns valid zero densities, because 'no warm
    words' is a real observation.
    """

    if not isinstance(content, str) or not content:
        return {}
    signals = read_signals(content)
    length = float(signals.length)
    clamped_length = privacy_clamp(18, length)
    if length <= clamped_length:
        # Common case: within channel 18's clamp, store the raw lexicon read
        # verbatim (a byte-exact no-op, so a short body's densities are unchanged).
        warm, cold, distress = signals.warm, signals.cold, signals.distress
        exclaim, punct, valence = signals.exclaim, signals.punct, signals.valence_cue
    else:
        # A >4096-char body: recover the integer hit COUNTS and re-normalize them by
        # the CLAMPED length.  ``read_signals`` divides counts by the true length, so
        # neither the value nor its low-order float bits may carry the true length
        # past channel 18's clamp -- recomputing from the count is length-invariant.
        inv = 10.0 / clamped_length

        def _count(density: float) -> int:
            return round(density * length / 10.0)

        warm, cold, distress = _count(signals.warm) * inv, _count(signals.cold) * inv, _count(signals.distress) * inv
        exclaim, punct = _count(signals.exclaim) * inv, _count(signals.punct) * inv
        valence = warm - cold
    return {
        18: clamped_length,                    # text.length (chars), privacy-clamped
        19: warm,                              # text.warm    density
        20: cold,                              # text.cold    density
        21: distress,                          # text.distress density
        22: 1.0 if signals.question else 0.0,  # text.question boolean
        23: exclaim,                           # text.exclaim density
        24: punct,                             # text.punct   density
        25: valence,                           # text.valence_cue (signed: warm - cold)
        26: float(signals.engagement_cue),     # text.engagement_cue ([0, ~1.3]); length-saturated at >=40
    }


def _project_messages(messages: list) -> tuple:
    """Derive bounded numeric channel facts from raw messages, discarding content."""

    turns: list[SourceTurn] = []
    sequence = 0
    for message in messages:
        if not isinstance(message, dict):
            continue
        role = message.get("role")
        if role != "user":
            continue
        content = message.get("content")
        sequence += 1
        values = [0.0] * OBSERVATION_DIM
        mask = 0
        # Text channels 18-26 come from the one canonical v2core lexicon (this is the
        # privacy projection: text in, bounded scalars out, text discarded).  channel
        # 13 is body.epoch and 31 is gap_seconds -- neither has an offline fact, so
        # they stay invalid; the reaction signal treats a missing gap as the neutral
        # 1.0 attenuator (spec §1.3), declared in the manifest via
        # OFFLINE_UNAVAILABLE_CHANNELS.  channel 30 is the structural has-history flag.
        facts = _lexicon_channel_facts(content)
        facts[30] = 1.0 if sequence > 1 else 0.0
        for channel, value in facts.items():
            values[channel] = float(value)
            mask |= 1 << channel
        turns.append(
            SourceTurn(
                values=tuple(values),
                valid_mask=mask,
                context="ADDRESSED",
                actual_action="UNKNOWN",  # offline history carries no structured receipt
                writer_epoch=1,
                local_sequence=sequence,
                dropped_gap_count=0,
                # A single conversation_id is one conversant, so t+1 is always the same
                # sender as t (private-chat semantics, spec §1.3).
                reaction_same_sender=True,
                source_components=(str(sequence),),
            )
        )
    return tuple(turns)


def export_real_history(
    *,
    data_dir: Path,
    output: Path,
    manifest_path: Path,
    link_key: EvaluationLinkKey,
    provenance_class: str = "REAL_LOCAL_HISTORY_V1",
    gate_manifest_digest: str | None = None,
) -> ExportResult:
    if link_key.synthetic:
        raise ExportRefused(
            "the synthetic link key is published and must never group real history"
        )
    if provenance_class not in PROVENANCE_CLASSES:
        raise ExportRefused(f"provenance class {provenance_class!r} is not declared")
    if not tracked_tree_is_clean():
        raise ExportRefused("real exports require a clean tracked tree naming this HEAD")

    episodes, corpus, _ = read_local_history(data_dir)
    if not episodes:
        raise ExportRefused("no exportable episodes were found in the supplied data directory")
    source_key = _mint_source_key()
    source_key_id = f"source-{secrets.token_hex(8)}"
    dataset_id = secrets.token_bytes(16)
    digest = gate_manifest_digest or default_gate_manifest_digest()
    rows = _build_records(
        episodes,
        link_key=link_key,
        source_key=source_key,
        dataset_id=dataset_id,
        provenance_class=provenance_class,
        gate_manifest_digest=digest,
    )
    manifest = _write_export(
        rows,
        output=Path(output),
        manifest_path=Path(manifest_path),
        link_key=link_key,
        source_key=source_key,
        source_key_id=source_key_id,
        dataset_id=dataset_id,
        provenance_class=provenance_class,
        gate_manifest_digest=digest,
        source_corpus=corpus,
        offline_unavailable_channels=OFFLINE_UNAVAILABLE_CHANNELS,
    )
    destroy_source_key(source_key)
    return ExportResult(
        output=Path(output),
        manifest_path=Path(manifest_path),
        manifest=manifest,
        source_corpus_bytes=corpus,
        source_identifiers=tuple(),
        source_key_material=None,
    )


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export an encoded v3 evaluation dataset.")
    parser.add_argument("--astrbot-data-dir", default=None)
    parser.add_argument("--synthetic", action="store_true", help="export a synthetic corpus")
    parser.add_argument("--seed", type=int, default=2718)
    parser.add_argument("--groups", type=int, default=24)
    parser.add_argument("--episodes-per-group", type=int, default=2)
    parser.add_argument("--turns-per-episode", type=int, default=12)
    parser.add_argument("--evaluation-link-key", default=None)
    parser.add_argument("--create-evaluation-link-key", action="store_true")
    parser.add_argument("--require-existing-evaluation-link-key", action="store_true")
    parser.add_argument("--require-build-channel", default=None)
    parser.add_argument("--only-provable-correlation", action="store_true")
    parser.add_argument("--provenance-class", default="REAL_LOCAL_HISTORY_V1")
    parser.add_argument("--gate-manifest", default=None)
    parser.add_argument("--output", required=True)
    parser.add_argument("--manifest", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    gate_digest = file_digest(Path(args.gate_manifest)) if args.gate_manifest else None

    if args.synthetic:
        result = export_synthetic(
            output=Path(args.output),
            manifest_path=Path(args.manifest),
            link_key=synthetic_link_key(args.seed),
            seed=args.seed,
            groups=args.groups,
            episodes_per_group=args.episodes_per_group,
            turns_per_episode=args.turns_per_episode,
            gate_manifest_digest=gate_digest,
        )
        print(f"synthetic export: {result.manifest['row_count']} rows -> {result.output}")
        return 0

    for flag, value in (
        ("--only-provable-correlation", args.only_provable_correlation),
        ("--require-build-channel", args.require_build_channel),
    ):
        if value:
            # These gate G3's identity (spec 17.1: "every turn with provable
            # request/terminal correlation"). Accepting and ignoring them would let
            # G4 believe a contract that was never applied. Refuse loudly instead.
            raise ExportRefused(
                f"{flag} is NOT IMPLEMENTED (G3 capture is post-candidate, plan Task 17). "
                "Refusing rather than silently exporting without the requested filter."
            )
    if args.evaluation_link_key is None:
        raise ExportRefused("--evaluation-link-key is required for a real export")
    key_path = Path(args.evaluation_link_key)
    if args.create_evaluation_link_key and args.require_existing_evaluation_link_key:
        raise ExportRefused("--create- and --require-existing- evaluation-link-key are exclusive")
    link_key = (
        create_evaluation_link_key(key_path)
        if args.create_evaluation_link_key
        else load_evaluation_link_key(key_path)
    )
    result = export_real_history(
        data_dir=resolve_data_dir(args.astrbot_data_dir),
        output=Path(args.output),
        manifest_path=Path(args.manifest),
        link_key=link_key,
        provenance_class=args.provenance_class,
        gate_manifest_digest=gate_digest,
    )
    print(f"export: {result.manifest['row_count']} rows -> {result.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
