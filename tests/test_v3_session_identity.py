from __future__ import annotations

import os
import re
import stat
from pathlib import Path

import pytest

import sylanne_alpha.v3bridge.session_identity as session_identity_module
from sylanne_alpha.v3bridge.session_identity import (
    MAX_SIGNED_64,
    SESSION_IDENTITY_MAX_COMPONENT_BYTES,
    SESSION_IDENTITY_MAX_KEY_ID_BYTES,
    SESSION_IDENTITY_MAX_SECRET_BYTES,
    SESSION_IDENTITY_MIN_SECRET_BYTES,
    SessionIdentityKey,
    load_or_create_session_identity_key,
    session_filename_token,
    session_trace_fields,
)


def _assert_owner_only(path: Path) -> None:
    if os.name != "nt":
        info = path.stat()
        assert stat.S_IMODE(info.st_mode) & 0o077 == 0
        assert info.st_uid == os.geteuid()
        return

    import ntsecuritycon
    import win32api
    import win32con
    import win32security

    token = win32security.OpenProcessToken(
        win32api.GetCurrentProcess(),
        win32con.TOKEN_QUERY,
    )
    try:
        current_sid = win32security.GetTokenInformation(
            token,
            win32security.TokenUser,
        )[0]
    finally:
        token.Close()
    allowed = {
        win32security.ConvertSidToStringSid(current_sid),
        win32security.ConvertSidToStringSid(
            win32security.CreateWellKnownSid(
                win32security.WinBuiltinAdministratorsSid,
                None,
            )
        ),
        win32security.ConvertSidToStringSid(
            win32security.CreateWellKnownSid(
                win32security.WinLocalSystemSid,
                None,
            )
        ),
    }
    descriptor = win32security.GetNamedSecurityInfo(
        str(path),
        win32security.SE_FILE_OBJECT,
        win32security.OWNER_SECURITY_INFORMATION | win32security.DACL_SECURITY_INFORMATION,
    )
    owner = descriptor.GetSecurityDescriptorOwner()
    dacl = descriptor.GetSecurityDescriptorDacl()
    control, _revision = descriptor.GetSecurityDescriptorControl()

    assert win32security.ConvertSidToStringSid(owner) == win32security.ConvertSidToStringSid(current_sid)
    assert dacl is not None
    assert control & win32security.SE_DACL_PROTECTED
    found: set[str] = set()
    for index in range(dacl.GetAceCount()):
        header, mask, sid = dacl.GetAce(index)
        ace_type, ace_flags = header
        assert ace_type == ntsecuritycon.ACCESS_ALLOWED_ACE_TYPE
        assert not ace_flags & win32security.INHERITED_ACE
        assert mask == ntsecuritycon.FILE_ALL_ACCESS
        sid_text = win32security.ConvertSidToStringSid(sid)
        assert sid_text in allowed
        found.add(sid_text)
    assert found == allowed
    assert dacl.GetAceCount() == 3


def test_session_identity_length_frames_ambiguous_component_boundaries() -> None:
    key = SessionIdentityKey(key_id="session-v1", secret=b"s" * 32)

    first = key.session_ref("qq", "a:b", session_generation=0)
    second = key.session_ref("qq:a", "b", session_generation=0)

    assert first != second


def test_session_identity_is_full_digest_and_never_exposes_raw_identifiers() -> None:
    secret = b"private-session-secret-material!"
    platform_id = "raw-platform-do-not-store"
    unified_msg_origin = "raw-umo-do-not-store"
    key = SessionIdentityKey(key_id="rotation-2026-07", secret=secret)

    session_ref = key.session_ref(platform_id, unified_msg_origin, session_generation=4)

    assert session_ref is not None
    assert len(session_ref.session_digest) == 32
    assert secret.decode() not in repr(key)
    assert platform_id not in repr(session_ref)
    assert unified_msg_origin not in repr(session_ref)
    token = session_filename_token(session_ref)
    assert re.fullmatch(r"s3-[0-9a-f]{64}", token)
    trace = session_trace_fields(session_ref)
    rendered = repr((token, trace))
    assert platform_id not in rendered
    assert unified_msg_origin not in rendered
    assert trace == {
        "key_id": "rotation-2026-07",
        "session_digest": session_ref.session_digest.hex(),
        "session_generation": 4,
    }


def test_session_identity_key_rotation_has_an_explicit_namespace() -> None:
    secret = b"s" * 32
    first_key = SessionIdentityKey(key_id="rotation-a", secret=secret)
    second_key = SessionIdentityKey(key_id="rotation-b", secret=secret)

    first = first_key.session_ref("qq", "umo", session_generation=0)
    rotated = second_key.session_ref("qq", "umo", session_generation=0)
    regenerated = first_key.session_ref("qq", "umo", session_generation=1)

    assert first is not None and rotated is not None and regenerated is not None
    assert first.session_digest != rotated.session_digest
    assert first.key_id != rotated.key_id
    assert first.session_digest == regenerated.session_digest
    assert first != regenerated


@pytest.mark.parametrize(
    ("platform_id", "unified_msg_origin"),
    [(None, "umo"), ("", "umo"), ("qq", None), ("qq", "")],
)
def test_session_identity_missing_stable_component_returns_unmatched(
    platform_id: object,
    unified_msg_origin: object,
) -> None:
    key = SessionIdentityKey(key_id="rotation-a", secret=b"s" * 32)

    assert key.session_ref(platform_id, unified_msg_origin, session_generation=0) is None


def test_correlation_digest_covers_all_three_stable_components() -> None:
    key = SessionIdentityKey(key_id="rotation-a", secret=b"s" * 32)

    baseline = key.correlation_digest("qq", "umo", "message")
    variants = {
        key.correlation_digest("qq-2", "umo", "message"),
        key.correlation_digest("qq", "umo-2", "message"),
        key.correlation_digest("qq", "umo", "message-2"),
        key.correlation_digest("qq:a", "b", "message"),
        key.correlation_digest("qq", "a:b", "message"),
    }

    assert baseline is not None
    assert len(baseline) == 32
    assert key.correlation_digest("qq", "umo", "message") == baseline
    assert baseline not in variants
    assert len(variants) == 5


@pytest.mark.parametrize(
    ("platform_id", "unified_msg_origin", "message_id"),
    [
        (None, "umo", "message"),
        ("", "umo", "message"),
        ("qq", None, "message"),
        ("qq", "", "message"),
        ("qq", "umo", None),
        ("qq", "umo", ""),
    ],
)
def test_correlation_missing_component_returns_unmatched(
    platform_id: object,
    unified_msg_origin: object,
    message_id: object,
) -> None:
    key = SessionIdentityKey(key_id="rotation-a", secret=b"s" * 32)

    assert key.correlation_digest(platform_id, unified_msg_origin, message_id) is None


def test_session_identity_rejects_wrong_semantic_types_and_bool_as_int() -> None:
    with pytest.raises(TypeError):
        SessionIdentityKey(key_id=True, secret=b"s" * 32)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        SessionIdentityKey(key_id="rotation-a", secret=bytearray(b"s" * 32))  # type: ignore[arg-type]

    key = SessionIdentityKey(key_id="rotation-a", secret=b"s" * 32)
    with pytest.raises(TypeError):
        key.session_ref("qq", "umo", session_generation=True)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        key.session_ref(["qq"], "umo", session_generation=0)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        key.correlation_digest("qq", object(), "message")  # type: ignore[arg-type]


def test_session_identity_secret_bounds_accept_edges_and_reject_weak_or_oversized_keys() -> None:
    assert SESSION_IDENTITY_MIN_SECRET_BYTES == 32
    assert SESSION_IDENTITY_MAX_SECRET_BYTES == 4096
    assert SessionIdentityKey(key_id="minimum", secret=b"s" * 32)
    assert SessionIdentityKey(key_id="maximum", secret=b"s" * 4096)

    with pytest.raises(ValueError):
        SessionIdentityKey(key_id="weak", secret=b"s" * 31)
    with pytest.raises(ValueError):
        SessionIdentityKey(key_id="oversized", secret=b"s" * 4097)


def test_session_identity_key_id_limit_is_measured_in_utf8_bytes() -> None:
    assert SESSION_IDENTITY_MAX_KEY_ID_BYTES == 128
    secret = b"s" * 32
    assert SessionIdentityKey(key_id="k" * 128, secret=secret)
    assert SessionIdentityKey(key_id="é" * 64, secret=secret)

    with pytest.raises(ValueError):
        SessionIdentityKey(key_id="k" * 129, secret=secret)
    with pytest.raises(ValueError):
        SessionIdentityKey(key_id="é" * 65, secret=secret)


def test_session_identity_component_limit_accepts_boundary_and_rejects_each_oversize_field() -> None:
    assert SESSION_IDENTITY_MAX_COMPONENT_BYTES == 4096
    key = SessionIdentityKey(key_id="bounded", secret=b"s" * 32)
    boundary = "é" * 2048
    oversized = "é" * 2049

    assert key.session_ref(boundary, boundary, session_generation=0) is not None
    assert key.correlation_digest(boundary, boundary, boundary) is not None
    with pytest.raises(ValueError):
        key.session_ref(oversized, "umo", session_generation=0)
    with pytest.raises(ValueError):
        key.session_ref("qq", oversized, session_generation=0)
    with pytest.raises(ValueError):
        key.correlation_digest(oversized, "umo", "message")
    with pytest.raises(ValueError):
        key.correlation_digest("qq", oversized, "message")
    with pytest.raises(ValueError):
        key.correlation_digest("qq", "umo", oversized)


def test_session_identity_generation_is_bounded_to_signed_64_bit() -> None:
    assert MAX_SIGNED_64 == (1 << 63) - 1
    key = SessionIdentityKey(key_id="bounded", secret=b"s" * 32)

    session_ref = key.session_ref("qq", "umo", session_generation=MAX_SIGNED_64)

    assert session_ref is not None
    assert session_ref.session_generation == MAX_SIGNED_64
    with pytest.raises(ValueError):
        key.session_ref("qq", "umo", session_generation=MAX_SIGNED_64 + 1)


def test_session_identity_rejects_very_long_ascii_components() -> None:
    key = SessionIdentityKey(key_id="bounded", secret=b"s" * 32)
    oversized = "x" * (SESSION_IDENTITY_MAX_COMPONENT_BYTES + 100_000)

    with pytest.raises(ValueError):
        key.session_ref(oversized, "umo", session_generation=0)
    with pytest.raises(ValueError):
        key.correlation_digest("qq", "umo", oversized)


def test_persistent_identity_key_is_stable_and_owner_only(tmp_path: Path) -> None:
    key_path = tmp_path / "identity" / "session.key"

    first = load_or_create_session_identity_key(key_path)
    second = load_or_create_session_identity_key(key_path)

    assert first == second
    assert first.session_ref("qq", "umo", session_generation=0) == second.session_ref("qq", "umo", session_generation=0)
    _assert_owner_only(key_path.parent)
    _assert_owner_only(key_path)
    assert first.secret not in repr(first).encode("utf-8")


def test_corrupt_persistent_identity_key_fails_closed_without_rotation(tmp_path: Path) -> None:
    key_path = tmp_path / "identity" / "session.key"
    key_path.parent.mkdir(parents=True)
    key_path.write_bytes(b"truncated")

    with pytest.raises(ValueError, match="identity key"):
        load_or_create_session_identity_key(key_path)
    assert key_path.read_bytes() == b"truncated"


@pytest.mark.skipif(os.name != "nt", reason="Windows ReadFile boundary only")
def test_windows_identity_key_read_rejects_non_bytes_before_payload_validation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import win32file

    key_path = tmp_path / "identity" / "session.key"
    load_or_create_session_identity_key(key_path)
    monkeypatch.setattr(
        win32file,
        "ReadFile",
        lambda _handle, _size: (0, "not-bytes"),
    )

    with pytest.raises(OSError, match="non-bytes payload"):
        load_or_create_session_identity_key(key_path)


def test_identity_key_creation_failure_never_leaves_a_partial_final_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    key_path = tmp_path / "identity" / "session.key"

    if os.name == "nt":

        def fail_flush(_handle: object) -> None:
            raise OSError("injected flush failure")

        monkeypatch.setattr(
            session_identity_module,
            "_flush_windows_handle",
            fail_flush,
            raising=False,
        )
    else:
        real_fsync = os.fsync
        calls = 0

        def fail_first_fsync(fd: int) -> None:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise OSError("injected flush failure")
            real_fsync(fd)

        monkeypatch.setattr(session_identity_module.os, "fsync", fail_first_fsync)

    with pytest.raises(OSError, match="flush failure"):
        load_or_create_session_identity_key(key_path)
    assert not key_path.exists()


def test_existing_identity_key_with_weak_permissions_fails_closed(tmp_path: Path) -> None:
    key_path = tmp_path / "identity" / "session.key"
    load_or_create_session_identity_key(key_path)

    if os.name == "nt":
        import ntsecuritycon
        import win32security

        descriptor = win32security.GetNamedSecurityInfo(
            str(key_path),
            win32security.SE_FILE_OBJECT,
            win32security.DACL_SECURITY_INFORMATION,
        )
        dacl = descriptor.GetSecurityDescriptorDacl()
        assert dacl is not None
        dacl.AddAccessAllowedAceEx(
            win32security.ACL_REVISION,
            0,
            ntsecuritycon.FILE_GENERIC_READ,
            win32security.CreateWellKnownSid(win32security.WinWorldSid, None),
        )
        win32security.SetNamedSecurityInfo(
            str(key_path),
            win32security.SE_FILE_OBJECT,
            win32security.DACL_SECURITY_INFORMATION | win32security.PROTECTED_DACL_SECURITY_INFORMATION,
            None,
            None,
            dacl,
            None,
        )
    else:
        key_path.chmod(0o644)

    with pytest.raises(ValueError, match="permission|ACL|owner"):
        load_or_create_session_identity_key(key_path)


def test_speaker_digest_is_domain_separated_and_never_exposes_raw_sender() -> None:
    key = SessionIdentityKey(key_id="session-v1", secret=b"s" * 32)
    speaker = key.speaker_digest("qq", "raw-user-2300184498")
    session = key.session_ref("qq", "raw-user-2300184498", session_generation=0)

    assert speaker is not None and len(speaker) == 32
    assert session is not None and speaker != session.session_digest
    assert b"raw-user-2300184498" not in speaker
    assert key.speaker_digest("qq", None) is None
