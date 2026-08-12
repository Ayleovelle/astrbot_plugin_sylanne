"""Deterministic opaque scope fixtures shared by scope-isolation tests."""

from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass

import pytest

from sylanne_alpha.scope_contracts import BotRef, PersonaRevisionRef, SessionRef, SessionScope


_DIGEST_A = "a" * 64
_DIGEST_B = "b" * 64
_DIGEST_C = "c" * 64
_DIGEST_D = "d" * 64


def scope_storage_token(label: str) -> str:
    """Return a deterministic test token with the production HMAC digest shape."""

    digest = hashlib.sha256(label.encode("utf-8")).digest()
    payload = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return f"scope_v1_{payload}"


def _bot(token: str) -> BotRef:
    return BotRef(token=token, generation=0)


def _persona(token: str, bot: BotRef, digest: str, *, lifecycle: int = 0) -> PersonaRevisionRef:
    return PersonaRevisionRef(
        token=token,
        bot_ref=bot,
        persona_id_digest=digest,
        source_fingerprint=digest,
        lifecycle_generation=lifecycle,
    )


def _scope(
    *,
    bot: BotRef,
    persona: PersonaRevisionRef,
    session_token: str,
    storage_token: str,
    scope_generation: int = 0,
) -> SessionScope:
    return SessionScope(
        bot_ref=bot,
        persona_ref=persona,
        session_ref=SessionRef(token=session_token, bot_ref=bot, generation=0),
        storage_token=storage_token,
        scope_generation=scope_generation,
    )


@dataclass(frozen=True, slots=True)
class ScopeFixtures:
    bot_a_persona_a: SessionScope
    bot_a_persona_b: SessionScope
    bot_a_persona_a_second_session: SessionScope
    bot_b_persona_a: SessionScope
    bot_a_persona_a_recreated: SessionScope


@pytest.fixture
def scopes() -> ScopeFixtures:
    """Build only synthetic opaque identifiers; no transport values or secrets."""

    bot_a = _bot("bot_v1_fixture_a")
    bot_b = _bot("bot_v1_fixture_b")
    persona_a = _persona("persona_v1_fixture_a", bot_a, _DIGEST_A)
    persona_b = _persona("persona_v1_fixture_b", bot_a, _DIGEST_B)
    other_bot_persona_a = _persona("persona_v1_fixture_c", bot_b, _DIGEST_C)
    recreated_persona_a = _persona(
        "persona_v1_fixture_a", bot_a, _DIGEST_D, lifecycle=1
    )
    return ScopeFixtures(
        bot_a_persona_a=_scope(
            bot=bot_a,
            persona=persona_a,
            session_token="session_v1_fixture_one",
            storage_token=scope_storage_token("fixture-one"),
        ),
        bot_a_persona_b=_scope(
            bot=bot_a,
            persona=persona_b,
            session_token="session_v1_fixture_one",
            storage_token=scope_storage_token("fixture-two"),
        ),
        bot_a_persona_a_second_session=_scope(
            bot=bot_a,
            persona=persona_a,
            session_token="session_v1_fixture_two",
            storage_token=scope_storage_token("fixture-three"),
        ),
        bot_b_persona_a=_scope(
            bot=bot_b,
            persona=other_bot_persona_a,
            session_token="session_v1_fixture_one",
            storage_token=scope_storage_token("fixture-four"),
        ),
        bot_a_persona_a_recreated=_scope(
            bot=bot_a,
            persona=recreated_persona_a,
            session_token="session_v1_fixture_one",
            storage_token=scope_storage_token("fixture-five"),
        ),
    )
