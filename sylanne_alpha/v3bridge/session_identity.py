"""Bridge-owned opaque session identities and safe persistence tokens."""

from __future__ import annotations

import hashlib
import hmac
import os
import stat
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, cast

from sylanne_alpha.v3core.canonical import canonical_sha256
from sylanne_alpha.v3core.contracts import SessionRef


_SESSION_DOMAIN = b"sylanne.v3bridge.session-ref.v1\x00"
_CORRELATION_DOMAIN = b"sylanne.v3bridge.response-correlation.v1\x00"
_SPEAKER_DOMAIN = b"sylanne.v3bridge.speaker-ref.v1\x00"
_PERSISTENT_KEY_MAGIC = b"SYLANNE-V3-SESSION-IDENTITY\x01\x00"
MAX_SIGNED_64 = (1 << 63) - 1
SESSION_IDENTITY_MIN_SECRET_BYTES = 32
SESSION_IDENTITY_MAX_SECRET_BYTES = 4096
SESSION_IDENTITY_MAX_KEY_ID_BYTES = 128
SESSION_IDENTITY_MAX_COMPONENT_BYTES = 4096


class _WindowsHandle(Protocol):
    def __int__(self) -> int: ...

    def Close(self) -> None: ...


class _WindowsAcl(Protocol):
    def GetAceCount(self) -> int: ...

    def GetAce(self, index: int, /) -> tuple[tuple[int, int], int, Any]: ...


class _WindowsSecurityDescriptor(Protocol):
    def GetSecurityDescriptorOwner(self) -> Any: ...

    def GetSecurityDescriptorDacl(self) -> _WindowsAcl | None: ...

    def GetSecurityDescriptorControl(self) -> tuple[int, int]: ...


def _frame(value: bytes) -> bytes:
    if len(value) > 0xFFFFFFFF:
        raise ValueError("identity component exceeds u32 framing")
    return len(value).to_bytes(4, "big") + value


def _text_bytes(value: object, name: str, *, max_bytes: int) -> bytes:
    if type(value) is not str:
        raise TypeError(f"{name} must have exact type str")
    if not value:
        raise ValueError(f"{name} must not be empty")
    if len(value) > max_bytes:
        raise ValueError(f"{name} exceeds {max_bytes} UTF-8 bytes")
    encoded = value.encode("utf-8")
    if len(encoded) > max_bytes:
        raise ValueError(f"{name} exceeds {max_bytes} UTF-8 bytes")
    return encoded


def _optional_text_bytes(value: object, name: str) -> bytes | None:
    if value is None:
        return None
    if type(value) is not str:
        raise TypeError(f"{name} must have exact type str or be missing")
    if not value:
        return None
    if len(value) > SESSION_IDENTITY_MAX_COMPONENT_BYTES:
        raise ValueError(f"{name} exceeds {SESSION_IDENTITY_MAX_COMPONENT_BYTES} UTF-8 bytes")
    encoded = value.encode("utf-8")
    if len(encoded) > SESSION_IDENTITY_MAX_COMPONENT_BYTES:
        raise ValueError(f"{name} exceeds {SESSION_IDENTITY_MAX_COMPONENT_BYTES} UTF-8 bytes")
    return encoded


@dataclass(frozen=True, slots=True)
class SessionIdentityKey:
    """Bridge-only HMAC key; its secret is never represented or exported."""

    key_id: str
    secret: bytes = field(repr=False)

    def __post_init__(self) -> None:
        _text_bytes(
            self.key_id,
            "key_id",
            max_bytes=SESSION_IDENTITY_MAX_KEY_ID_BYTES,
        )
        if type(self.secret) is not bytes:
            raise TypeError("secret must have exact type bytes")
        if not SESSION_IDENTITY_MIN_SECRET_BYTES <= len(self.secret) <= SESSION_IDENTITY_MAX_SECRET_BYTES:
            raise ValueError(
                "secret length must be within "
                f"[{SESSION_IDENTITY_MIN_SECRET_BYTES}, {SESSION_IDENTITY_MAX_SECRET_BYTES}] bytes"
            )

    def session_ref(
        self,
        platform_id: object,
        unified_msg_origin: object,
        *,
        session_generation: int,
    ) -> SessionRef | None:
        if type(session_generation) is not int:
            raise TypeError("session_generation must have exact type int")
        if not 0 <= session_generation <= MAX_SIGNED_64:
            raise ValueError("session_generation must be a signed 64-bit non-negative integer")
        platform_bytes = _optional_text_bytes(platform_id, "platform_id")
        origin_bytes = _optional_text_bytes(unified_msg_origin, "unified_msg_origin")
        if platform_bytes is None or origin_bytes is None:
            return None
        payload = b"".join(
            (
                _SESSION_DOMAIN,
                _frame(
                    _text_bytes(
                        self.key_id,
                        "key_id",
                        max_bytes=SESSION_IDENTITY_MAX_KEY_ID_BYTES,
                    )
                ),
                _frame(platform_bytes),
                _frame(origin_bytes),
            )
        )
        digest = hmac.new(self.secret, payload, hashlib.sha256).digest()
        return SessionRef(
            key_id=self.key_id,
            session_digest=digest,
            session_generation=session_generation,
        )

    def correlation_digest(
        self,
        platform_id: object,
        unified_msg_origin: object,
        message_id: object,
    ) -> bytes | None:
        """Return an opaque stable response join key, or unmatched for missing input."""

        platform_bytes = _optional_text_bytes(platform_id, "platform_id")
        origin_bytes = _optional_text_bytes(unified_msg_origin, "unified_msg_origin")
        message_bytes = _optional_text_bytes(message_id, "message_id")
        if platform_bytes is None or origin_bytes is None or message_bytes is None:
            return None
        payload = b"".join(
            (
                _CORRELATION_DOMAIN,
                _frame(
                    _text_bytes(
                        self.key_id,
                        "key_id",
                        max_bytes=SESSION_IDENTITY_MAX_KEY_ID_BYTES,
                    )
                ),
                _frame(platform_bytes),
                _frame(origin_bytes),
                _frame(message_bytes),
            )
        )
        return hmac.new(self.secret, payload, hashlib.sha256).digest()

    def speaker_digest(self, platform_id: object, sender_id: object) -> bytes | None:
        """Return a domain-separated opaque speaker surrogate for equality only."""

        platform_bytes = _optional_text_bytes(platform_id, "platform_id")
        sender_bytes = _optional_text_bytes(sender_id, "sender_id")
        if platform_bytes is None or sender_bytes is None:
            return None
        payload = b"".join(
            (
                _SPEAKER_DOMAIN,
                _frame(
                    _text_bytes(
                        self.key_id,
                        "key_id",
                        max_bytes=SESSION_IDENTITY_MAX_KEY_ID_BYTES,
                    )
                ),
                _frame(platform_bytes),
                _frame(sender_bytes),
            )
        )
        return hmac.new(self.secret, payload, hashlib.sha256).digest()


def _persistent_key_id(secret: bytes) -> str:
    digest = hashlib.sha256(b"sylanne.v3bridge.identity-key-id.v1\x00" + secret).hexdigest()
    return f"session-key-v1-{digest[:32]}"


def _write_all(fd: int, data: bytes) -> None:
    view = memoryview(data)
    offset = 0
    while offset < len(view):
        written = os.write(fd, view[offset:])
        if written <= 0:
            raise OSError("identity key write made no progress")
        offset += written


def _validate_payload(data: bytes) -> bytes:
    if not data.startswith(_PERSISTENT_KEY_MAGIC):
        raise ValueError("identity key has an invalid header")
    secret = data[len(_PERSISTENT_KEY_MAGIC) :]
    if len(secret) != SESSION_IDENTITY_MIN_SECRET_BYTES:
        raise ValueError("identity key has an invalid length")
    return secret


def _sync_parent_if_supported(path: Path) -> None:
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def _current_effective_uid() -> int:
    get_effective_uid = getattr(os, "geteuid", None)
    if not callable(get_effective_uid):
        raise OSError("effective user identity is unavailable on this platform")
    uid = get_effective_uid()
    if type(uid) is not int:
        raise OSError("effective user identity has an invalid type")
    return uid


def _validate_posix_owner_only(path: Path, *, directory: bool) -> os.stat_result:
    try:
        info = path.lstat()
    except OSError as exc:
        raise ValueError("identity key permissions could not be inspected") from exc
    expected = stat.S_ISDIR if directory else stat.S_ISREG
    if not expected(info.st_mode) or stat.S_ISLNK(info.st_mode):
        raise ValueError("identity key path has an invalid file type")
    if info.st_uid != _current_effective_uid():
        raise ValueError("identity key owner does not match the current user")
    if stat.S_IMODE(info.st_mode) & 0o077:
        raise ValueError("identity key permissions are not owner-only")
    if not directory and info.st_nlink != 1:
        raise ValueError("identity key must have exactly one hard link")
    return info


def _load_posix_secret(path: Path) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise ValueError("identity key could not be opened securely") from exc
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != _current_effective_uid():
            raise ValueError("identity key owner or file type is invalid")
        if stat.S_IMODE(info.st_mode) & 0o077 or info.st_nlink != 1:
            raise ValueError("identity key permissions are not owner-only")
        maximum = len(_PERSISTENT_KEY_MAGIC) + SESSION_IDENTITY_MIN_SECRET_BYTES + 1
        chunks: list[bytes] = []
        remaining = maximum
        while remaining > 0:
            chunk = os.read(fd, remaining)
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        return _validate_payload(b"".join(chunks))
    finally:
        os.close(fd)


def _windows_security_attributes():
    import ntsecuritycon
    import pywintypes
    import win32api
    import win32con
    import win32security

    token = cast(
        _WindowsHandle,
        win32security.OpenProcessToken(
            win32api.GetCurrentProcess(),
            win32con.TOKEN_QUERY,
        ),
    )
    try:
        owner_sid = win32security.GetTokenInformation(
            int(token),
            win32security.TokenUser,
        )[0]
    finally:
        token.Close()
    admin_sid = win32security.CreateWellKnownSid(
        win32security.WinBuiltinAdministratorsSid,
        None,
    )
    system_sid = win32security.CreateWellKnownSid(
        win32security.WinLocalSystemSid,
        None,
    )
    dacl = pywintypes.ACL()
    for sid in (owner_sid, admin_sid, system_sid):
        dacl.AddAccessAllowedAceEx(
            win32security.ACL_REVISION,
            0,
            ntsecuritycon.FILE_ALL_ACCESS,
            sid,
        )
    descriptor = pywintypes.SECURITY_DESCRIPTOR()
    descriptor.SetSecurityDescriptorOwner(owner_sid, False)
    descriptor.SetSecurityDescriptorDacl(True, dacl, False)
    descriptor.SetSecurityDescriptorControl(
        win32security.SE_DACL_PROTECTED,
        win32security.SE_DACL_PROTECTED,
    )
    attributes = pywintypes.SECURITY_ATTRIBUTES()
    attributes.bInheritHandle = False
    attributes.SECURITY_DESCRIPTOR = descriptor
    return attributes, owner_sid, dacl


def _validate_windows_descriptor(descriptor: _WindowsSecurityDescriptor) -> None:
    import ntsecuritycon
    import win32security

    _attributes, owner_sid, _dacl = _windows_security_attributes()
    sid_text = win32security.ConvertSidToStringSid
    allowed = {
        sid_text(owner_sid),
        sid_text(
            win32security.CreateWellKnownSid(
                win32security.WinBuiltinAdministratorsSid,
                None,
            )
        ),
        sid_text(
            win32security.CreateWellKnownSid(
                win32security.WinLocalSystemSid,
                None,
            )
        ),
    }
    owner = descriptor.GetSecurityDescriptorOwner()
    dacl = descriptor.GetSecurityDescriptorDacl()
    control, _revision = descriptor.GetSecurityDescriptorControl()
    if sid_text(owner) != sid_text(owner_sid):
        raise ValueError("identity key owner does not match the current user")
    if dacl is None or not control & win32security.SE_DACL_PROTECTED:
        raise ValueError("identity key ACL is missing or inherits permissions")
    found: set[str] = set()
    for index in range(dacl.GetAceCount()):
        header, mask, sid = dacl.GetAce(index)
        ace_type, ace_flags = header
        resolved = sid_text(sid)
        if (
            ace_type != ntsecuritycon.ACCESS_ALLOWED_ACE_TYPE
            or ace_flags & win32security.INHERITED_ACE
            or mask != ntsecuritycon.FILE_ALL_ACCESS
            or resolved not in allowed
        ):
            raise ValueError("identity key ACL contains an unauthorized entry")
        found.add(resolved)
    if found != allowed or dacl.GetAceCount() != len(allowed):
        raise ValueError("identity key ACL is not the exact owner-only policy")


def _validate_windows_path(path: Path) -> None:
    import win32security

    descriptor = win32security.GetNamedSecurityInfo(
        str(path),
        win32security.SE_FILE_OBJECT,
        win32security.OWNER_SECURITY_INFORMATION | win32security.DACL_SECURITY_INFORMATION,
    )
    _validate_windows_descriptor(descriptor)


def _secure_windows_parent(path: Path, *, key_exists: bool) -> None:
    import pywintypes
    import win32file
    import win32security
    import winerror

    path.parent.mkdir(parents=True, exist_ok=True)
    attributes, owner_sid, dacl = _windows_security_attributes()
    try:
        win32file.CreateDirectory(str(path), attributes)
    except pywintypes.error as exc:
        if exc.winerror not in {winerror.ERROR_ALREADY_EXISTS, winerror.ERROR_FILE_EXISTS}:
            raise
        if not key_exists:
            current = win32security.GetNamedSecurityInfo(
                str(path),
                win32security.SE_FILE_OBJECT,
                win32security.OWNER_SECURITY_INFORMATION,
            )
            current_owner = current.GetSecurityDescriptorOwner()
            if win32security.ConvertSidToStringSid(current_owner) != win32security.ConvertSidToStringSid(owner_sid):
                raise ValueError("identity key directory owner is invalid")
            win32security.SetNamedSecurityInfo(
                str(path),
                win32security.SE_FILE_OBJECT,
                win32security.DACL_SECURITY_INFORMATION | win32security.PROTECTED_DACL_SECURITY_INFORMATION,
                None,
                None,
                dacl,
                None,
            )
    _validate_windows_path(path)


def _flush_windows_handle(handle: _WindowsHandle) -> None:
    import win32file

    win32file.FlushFileBuffers(int(handle))


def _load_windows_secret(path: Path) -> bytes:
    import win32con
    import win32file
    import win32security

    attributes = win32file.GetFileAttributes(str(path))
    if attributes & win32con.FILE_ATTRIBUTE_REPARSE_POINT:
        raise ValueError("identity key path must not be a reparse point")
    handle: _WindowsHandle = win32file.CreateFile(
        str(path),
        win32con.GENERIC_READ | win32con.READ_CONTROL,
        win32con.FILE_SHARE_READ,
        None,
        win32con.OPEN_EXISTING,
        win32con.FILE_ATTRIBUTE_NORMAL | win32file.FILE_FLAG_OPEN_REPARSE_POINT,
        None,
    )
    try:
        descriptor = win32security.GetSecurityInfo(
            int(handle),
            win32security.SE_FILE_OBJECT,
            win32security.OWNER_SECURITY_INFORMATION | win32security.DACL_SECURITY_INFORMATION,
        )
        _validate_windows_descriptor(descriptor)
        result, data = cast(
            tuple[int, object],
            win32file.ReadFile(
                int(handle),
                len(_PERSISTENT_KEY_MAGIC) + SESSION_IDENTITY_MIN_SECRET_BYTES + 1,
            ),
        )
        if result != 0:
            raise OSError(f"identity key read failed with status {result}")
        if type(data) is not bytes:
            raise OSError("identity key read returned a non-bytes payload")
        return _validate_payload(data)
    finally:
        handle.Close()


def _create_windows_secret(path: Path, payload: bytes) -> bytes:
    import pywintypes
    import win32con
    import win32file
    import win32security
    import winerror

    temp_path = path.with_name(f".{path.name}.{os.urandom(12).hex()}.tmp")
    attributes, _owner_sid, _dacl = _windows_security_attributes()
    try:
        handle: _WindowsHandle = win32file.CreateFile(
            str(temp_path),
            win32con.GENERIC_WRITE | win32con.READ_CONTROL,
            0,
            attributes,
            win32con.CREATE_NEW,
            win32con.FILE_ATTRIBUTE_NORMAL,
            None,
        )
        try:
            descriptor = win32security.GetSecurityInfo(
                int(handle),
                win32security.SE_FILE_OBJECT,
                win32security.OWNER_SECURITY_INFORMATION | win32security.DACL_SECURITY_INFORMATION,
            )
            _validate_windows_descriptor(descriptor)
            result, written = win32file.WriteFile(int(handle), payload)
            if result != 0 or written != len(payload):
                raise OSError("identity key write was incomplete")
            _flush_windows_handle(handle)
        finally:
            handle.Close()
        try:
            win32file.MoveFileEx(
                str(temp_path),
                str(path),
                win32file.MOVEFILE_WRITE_THROUGH,
            )
        except pywintypes.error as exc:
            if exc.winerror not in {
                winerror.ERROR_ALREADY_EXISTS,
                winerror.ERROR_FILE_EXISTS,
            }:
                raise
    finally:
        try:
            win32file.DeleteFile(str(temp_path))
        except pywintypes.error as exc:
            if exc.winerror != winerror.ERROR_FILE_NOT_FOUND:
                raise
    return _load_windows_secret(path)


def _load_persistent_secret(path: Path) -> bytes:
    if os.name == "nt":
        return _load_windows_secret(path)
    return _load_posix_secret(path)


def _create_posix_secret(path: Path, payload: bytes) -> bytes:
    temp_path = path.with_name(f".{path.name}.{os.urandom(12).hex()}.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    fd = os.open(temp_path, flags, 0o600)
    try:
        _write_all(fd, payload)
        os.fsync(fd)
    finally:
        os.close(fd)
    try:
        os.link(temp_path, path, follow_symlinks=False)
    except FileExistsError:
        pass
    finally:
        temp_path.unlink(missing_ok=True)
    _sync_parent_if_supported(path.parent)
    return _load_posix_secret(path)


def load_or_create_session_identity_key(path: str | os.PathLike[str]) -> SessionIdentityKey:
    """Load the stable bridge HMAC key, creating it once with owner-only access.

    A missing file creates a fresh namespace. A present but malformed file fails
    closed and is never silently replaced, so corruption cannot attach old state to
    a different identity.
    """

    key_path = Path(path)
    key_exists = key_path.exists()
    if os.name == "nt":
        _secure_windows_parent(key_path.parent, key_exists=key_exists)
    else:
        key_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if not key_exists:
            os.chmod(key_path.parent, 0o700)
        _validate_posix_owner_only(key_path.parent, directory=True)
    if key_exists:
        secret = _load_persistent_secret(key_path)
        return SessionIdentityKey(key_id=_persistent_key_id(secret), secret=secret)

    secret = os.urandom(SESSION_IDENTITY_MIN_SECRET_BYTES)
    payload = _PERSISTENT_KEY_MAGIC + secret
    if os.name == "nt":
        secret = _create_windows_secret(key_path, payload)
    else:
        secret = _create_posix_secret(key_path, payload)
    return SessionIdentityKey(key_id=_persistent_key_id(secret), secret=secret)


def session_filename_token(session_ref: SessionRef) -> str:
    """Return a path-safe token derived only from the opaque SessionRef."""

    if type(session_ref) is not SessionRef:
        raise TypeError("session_ref must have exact type SessionRef")
    digest = canonical_sha256(
        {
            "domain": "sylanne.v3bridge.session-filename.v1",
            "session_ref": session_trace_fields(session_ref),
        }
    )
    return f"s3-{digest}"


def session_trace_fields(session_ref: SessionRef) -> dict[str, object]:
    """Project the canonical raw-identifier-free session trace fields."""

    if type(session_ref) is not SessionRef:
        raise TypeError("session_ref must have exact type SessionRef")
    return {
        "key_id": session_ref.key_id,
        "session_digest": session_ref.session_digest.hex(),
        "session_generation": session_ref.session_generation,
    }


__all__ = [
    "MAX_SIGNED_64",
    "SESSION_IDENTITY_MAX_COMPONENT_BYTES",
    "SESSION_IDENTITY_MAX_KEY_ID_BYTES",
    "SESSION_IDENTITY_MAX_SECRET_BYTES",
    "SESSION_IDENTITY_MIN_SECRET_BYTES",
    "SessionIdentityKey",
    "load_or_create_session_identity_key",
    "session_filename_token",
    "session_trace_fields",
]
