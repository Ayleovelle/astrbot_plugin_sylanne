"""Task-6 subject-proof contracts before ingress activation."""

from __future__ import annotations

import json
from dataclasses import FrozenInstanceError, asdict, is_dataclass

import pytest

from sylanne_alpha.scope_contracts import (
    AuthenticatedSubject,
    TurnSubjectProof,
    VerifiedSubjectInput,
)
from sylanne_alpha.scope_identity import BotBinding, PersonaSource, ScopeIdentityKey
from sylanne_alpha.scope_runtime import RequestRuntimeView, ScopeRuntimeRegistry
from tests.scope_fixtures import scopes


def _identity() -> ScopeIdentityKey:
    return ScopeIdentityKey(key_id="scope-key-task6", secret=b"r" * 32)


def _resolved(scope):
    from sylanne_alpha.scope_contracts import ResolvedScope

    return ResolvedScope(
        scope=scope,
        persona_source=PersonaSource(
            persona_id="task6-subject-proof",
            prompt="quiet",
            begin_dialogs=(),
            tools=None,
            skills=None,
            resolution_source="test",
        ),
        identity_quality="event_self_id",
        resolution_source="test",
        resolved_at_ms=1,
        private_scope_enabled=True,
        disabled_reason=None,
        turn_generation=4,
    )


def test_authenticated_subject_discards_raw_sender_and_serializable_proof_material(scopes) -> None:
    identity = _identity()
    raw_sender = "RAW-SENDER-ID-DO-NOT-LOG"
    raw_platform = "RAW-PLATFORM-REALM-DO-NOT-STORE"
    candidate = VerifiedSubjectInput(
        platform_realm=raw_platform,
        subject_id=raw_sender,
    )

    subject = identity.authenticated_subject(scopes.bot_a_persona_a.bot_ref, candidate)

    assert type(subject) is AuthenticatedSubject
    assert subject is not None
    assert subject.relation_ref.bot_ref == scopes.bot_a_persona_a.bot_ref
    assert is_dataclass(candidate) and is_dataclass(subject)
    assert raw_sender not in repr(candidate)
    assert raw_sender not in repr(subject)
    serialized_subject = json.dumps(asdict(subject), sort_keys=True)
    assert raw_sender not in serialized_subject
    assert raw_platform not in serialized_subject

    proof = TurnSubjectProof(
        transport_session_token=scopes.bot_a_persona_a.session_ref.token,
        turn_generation=4,
        subject=subject,
    )
    serialized_proof = json.dumps(asdict(proof), sort_keys=True)
    assert raw_sender not in repr(proof)
    assert raw_sender not in serialized_proof
    assert raw_platform not in serialized_proof
    with pytest.raises(FrozenInstanceError):
        proof.turn_generation = 5  # type: ignore[misc]


def test_subject_proof_constructors_fail_closed_on_bad_tokens_generations_and_quality(scopes) -> None:
    identity = _identity()
    bot = scopes.bot_a_persona_a.bot_ref
    verified = VerifiedSubjectInput(platform_realm="adapter", subject_id="sender-1")
    subject = identity.authenticated_subject(bot, verified)
    assert subject is not None

    with pytest.raises(ValueError, match="subject_id"):
        VerifiedSubjectInput(platform_realm="adapter", subject_id="")
    with pytest.raises(ValueError, match="subject_kind"):
        VerifiedSubjectInput(platform_realm="adapter", subject_kind="group", subject_id="sender-1")
    with pytest.raises(ValueError, match="identity_quality"):
        VerifiedSubjectInput(platform_realm="adapter", subject_id="sender-1", identity_quality="")
    with pytest.raises(ValueError, match="identity_quality"):
        AuthenticatedSubject(relation_ref=subject.relation_ref, identity_quality="untrusted")
    with pytest.raises(ValueError, match="session_v1_"):
        TurnSubjectProof(
            transport_session_token="not-a-session-token",
            turn_generation=0,
            subject=subject,
        )
    with pytest.raises(ValueError, match="turn_generation"):
        TurnSubjectProof(
            transport_session_token=scopes.bot_a_persona_a.session_ref.token,
            turn_generation=True,  # type: ignore[arg-type]
            subject=subject,
        )


def test_missing_authenticated_subject_is_an_explicit_frozen_turn_proof(scopes) -> None:
    proof = TurnSubjectProof(
        transport_session_token=scopes.bot_a_persona_a.session_ref.token,
        turn_generation=4,
        subject=None,
    )

    assert proof.subject is None
    with pytest.raises(FrozenInstanceError):
        proof.subject = AuthenticatedSubject(  # type: ignore[misc]
            relation_ref=_identity()
            .authenticated_subject(
                scopes.bot_a_persona_a.bot_ref,
                VerifiedSubjectInput(platform_realm="adapter", subject_id="sender-1"),
            )
            .relation_ref,
            identity_quality="event_get_sender_id",
        )


def test_untrusted_subject_material_cannot_construct_a_verified_input() -> None:
    with pytest.raises(ValueError, match="identity_quality"):
        VerifiedSubjectInput(
            platform_realm="adapter",
            subject_id="sender-1",
            identity_quality="untrusted",
        )


def test_request_runtime_view_requires_one_matching_frozen_parent_scope(scopes) -> None:
    registry = ScopeRuntimeRegistry.for_test()
    scope = scopes.bot_a_persona_a
    matching = RequestRuntimeView(
        resolved=_resolved(scope),
        persona_runtime=registry.for_scope(scope),
        session_runtime=registry.exact_session(scope),
        relation_runtime=None,
    )

    assert matching.resolved.scope == scope
    with pytest.raises(FrozenInstanceError):
        matching.relation_runtime = None  # type: ignore[misc]

    other = scopes.bot_a_persona_b
    with pytest.raises(ValueError, match="parent scope"):
        RequestRuntimeView(
            resolved=_resolved(scope),
            persona_runtime=registry.for_scope(scope),
            session_runtime=registry.exact_session(other),
            relation_runtime=None,
        )
