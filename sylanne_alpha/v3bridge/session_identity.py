"""Bridge-owned opaque session identities and safe persistence tokens."""

from __future__ import annotations

import hashlib
import hmac
import os
from dataclasses import dataclass, field
from typing import Protocol

from sylanne_alpha.v3core.canonical import canonical_sha256
from sylanne_alpha.v3core.contracts import SessionRef

_SESSION_DOMAIN = b"sylanne.v3bridge.session-ref.v1\x00"
_CORRELATION_DOMAIN = b"sylanne.v3bridge.response-correlation.v1\x00"
_SPEAKER_DOMAIN = b"sylanne.v3bridge.speaker-ref.v1\x00"
_PERSISTENT_KEY_MAGIC = b"SYLANNE-V3-SESSION-IDENTITY\x01\x00"
SCOPE_V1_AUTHORITY = False
MAX_SIGNED_64 = (1 << 63) - 1
SESSION_IDENTITY_MIN_SECRET_BYTES = 32
SESSION_IDENTITY_MAX_SECRET_BYTES = 4096
SESSION_IDENTITY_MAX_KEY_ID_BYTES = 128
SESSION_IDENTITY_MAX_COMPONENT_BYTES = 4096


class _WindowsHandle(Protocol):
    def __int__(self) -> int: ...

    def Close(self) -> None: ...


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
        raise ValueError(
            f"{name} exceeds {SESSION_IDENTITY_MAX_COMPONENT_BYTES} UTF-8 bytes"
        )
    encoded = value.encode("utf-8")
    if len(encoded) > SESSION_IDENTITY_MAX_COMPONENT_BYTES:
        raise ValueError(
            f"{name} exceeds {SESSION_IDENTITY_MAX_COMPONENT_BYTES} UTF-8 bytes"
        )
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
        if not (
            SESSION_IDENTITY_MIN_SECRET_BYTES
            <= len(self.secret)
            <= SESSION_IDENTITY_MAX_SECRET_BYTES
        ):
            raise ValueError(
                "secret length must be within "
                f"[{SESSION_IDENTITY_MIN_SECRET_BYTES}, "
                f"{SESSION_IDENTITY_MAX_SECRET_BYTES}] bytes"
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
            raise ValueError(
                "session_generation must be a signed 64-bit non-negative integer"
            )
        platform_bytes = _optional_text_bytes(platform_id, "platform_id")
        origin_bytes = _optional_text_bytes(
            unified_msg_origin,
            "unified_msg_origin",
        )
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
        origin_bytes = _optional_text_bytes(
            unified_msg_origin,
            "unified_msg_origin",
        )
        message_bytes = _optional_text_bytes(message_id, "message_id")
        if (
            platform_bytes is None
            or origin_bytes is None
            or message_bytes is None
        ):
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

    def speaker_digest(
        self,
        platform_id: object,
        sender_id: object,
    ) -> bytes | None:
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
    digest = hashlib.sha256(
        b"sylanne.v3bridge.identity-key-id.v1\x00" + secret
    ).hexdigest()
    return f"session-key-v1-{digest[:32]}"


def _flush_windows_handle(handle: _WindowsHandle) -> None:
    """Compatibility seam retained for V3 Windows fault-injection tests."""

    import win32file

    win32file.FlushFileBuffers(int(handle))


def load_or_create_session_identity_key(
    path: str | os.PathLike[str],
) -> SessionIdentityKey:
    """Load the stable bridge HMAC key, creating it once with owner-only access.

    A missing file creates a fresh namespace. A present but malformed file fails
    closed and is never silently replaced, so corruption cannot attach old state to
    a different identity.
    """

    # Keep StateRepository/session-token imports light in spawned workers.
    from sylanne_alpha.infra import load_or_create_owner_only_secret

    secret = load_or_create_owner_only_secret(
        path,
        magic=_PERSISTENT_KEY_MAGIC,
        secret_bytes=SESSION_IDENTITY_MIN_SECRET_BYTES,
        error_label="identity key",
        # Keep the historical module-level monkeypatch seam alive.
        flush_windows_handle=_flush_windows_handle,
    )
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
    "SCOPE_V1_AUTHORITY",
    "SESSION_IDENTITY_MAX_COMPONENT_BYTES",
    "SESSION_IDENTITY_MAX_KEY_ID_BYTES",
    "SESSION_IDENTITY_MAX_SECRET_BYTES",
    "SESSION_IDENTITY_MIN_SECRET_BYTES",
    "SessionIdentityKey",
    "load_or_create_session_identity_key",
    "session_filename_token",
    "session_trace_fields",
]
