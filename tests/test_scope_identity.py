from __future__ import annotations

import pytest

import sylanne_alpha.v3bridge.session_identity as v3_session_identity
from sylanne_alpha.scope_contracts import BotRef
from sylanne_alpha.scope_identity import (
    AdapterAccountProof,
    BotBinding,
    CurrentAdapterAccountProof,
    NoAdapterAccountProofProvider,
    PersonaSource,
    ScopeIdentityKey,
    _frame,
    resolve_proven_single_account,
)


def _key() -> ScopeIdentityKey:
    return ScopeIdentityKey(key_id="scope-key-2026", secret=b"k" * 32)


def _source(
    *,
    persona_id: str = "persona.main",
    prompt: str = "A concise assistant.",
    tools: tuple[str, ...] | None = None,
    skills: tuple[str, ...] | None = None,
) -> PersonaSource:
    return PersonaSource(
        persona_id=persona_id,
        prompt=prompt,
        begin_dialogs=("hello",),
        tools=tools,
        skills=skills,
        resolution_source="catalog",
    )


def test_bot_and_session_identity_include_the_bound_platform_account() -> None:
    key = _key()
    first_bot = key.bot_ref(BotBinding(platform_id="adapter", self_id="account-a"), generation=0)
    second_bot = key.bot_ref(BotBinding(platform_id="adapter", self_id="account-b"), generation=0)

    first_session = key.session_ref(first_bot, "adapter", "umo-1", generation=0)
    second_session = key.session_ref(second_bot, "adapter", "umo-1", generation=0)

    assert first_bot != second_bot
    assert first_session != second_session


def test_bot_derivation_is_deterministic_and_session_generation_is_versioned() -> None:
    key = _key()
    qq_bot = key.bot_ref(BotBinding(platform_id="qq", self_id="account-a"), generation=0)
    discord_bot = key.bot_ref(BotBinding(platform_id="discord", self_id="account-a"), generation=0)

    assert qq_bot != discord_bot
    assert qq_bot == key.bot_ref(BotBinding(platform_id="qq", self_id="account-a"), generation=0)
    session_v0 = key.session_ref(qq_bot, "qq", "umo-1", generation=0)
    assert session_v0 == key.session_ref(qq_bot, "qq", "umo-1", generation=0)
    assert session_v0 != key.session_ref(
        qq_bot,
        "qq",
        "umo-1",
        generation=1,
    )


def test_persona_source_preserves_none_vs_empty_tool_and_skill_semantics() -> None:
    key = _key()
    bot = key.bot_ref(BotBinding(platform_id="adapter", self_id="account-a"), generation=0)

    absent = key.persona_revision(bot, _source(tools=None, skills=None), lifecycle_generation=0)
    empty_tools = key.persona_revision(bot, _source(tools=(), skills=None), lifecycle_generation=0)
    empty_skills = key.persona_revision(bot, _source(tools=None, skills=()), lifecycle_generation=0)

    assert absent.token != empty_tools.token
    assert absent.token != empty_skills.token
    assert empty_tools.token != empty_skills.token


def test_persona_source_requires_a_tuple_for_begin_dialogs() -> None:
    with pytest.raises(ValueError, match="^begin_dialogs must be an exact tuple$"):
        PersonaSource(
            persona_id="persona.main",
            prompt="A concise assistant.",
            begin_dialogs=None,  # type: ignore[arg-type]
            tools=None,
            skills=None,
            resolution_source="catalog",
        )


def test_persona_revision_changes_with_prompt_or_persona_id() -> None:
    key = _key()
    bot = key.bot_ref(BotBinding(platform_id="adapter", self_id="account-a"), generation=0)

    baseline = key.persona_revision(bot, _source(), lifecycle_generation=0)
    changed_prompt = key.persona_revision(bot, _source(prompt="A detailed assistant."), lifecycle_generation=0)
    renamed = key.persona_revision(bot, _source(persona_id="persona.renamed"), lifecycle_generation=0)

    assert baseline.token != changed_prompt.token
    assert baseline.token != renamed.token


def test_persona_token_excludes_lifecycle_generation_but_revision_does_not() -> None:
    key = _key()
    bot = key.bot_ref(BotBinding(platform_id="adapter", self_id="account-a"), generation=0)
    source = _source()

    first = key.persona_revision(bot, source, lifecycle_generation=0)
    second = key.persona_revision(bot, source, lifecycle_generation=1)

    assert first.token == second.token
    assert first != second


def test_relation_identity_is_bound_to_the_bot_namespace() -> None:
    key = _key()
    first_bot = key.bot_ref(BotBinding(platform_id="adapter", self_id="account-a"), generation=0)
    second_bot = key.bot_ref(BotBinding(platform_id="adapter", self_id="account-b"), generation=0)

    assert key.relation_ref(first_bot, "adapter", "sender", "sender-1") != key.relation_ref(
        second_bot,
        "adapter",
        "sender",
        "sender-1",
    )


def test_managed_embodiment_personas_are_forbidden() -> None:
    key = _key()
    bot = key.bot_ref(BotBinding(platform_id="adapter", self_id="account-a"), generation=0)

    with pytest.raises(ValueError, match="^managed embodiment persona is forbidden$"):
        key.persona_revision(
            bot,
            _source(persona_id="sylanne_embodiment_managed"),
            lifecycle_generation=0,
        )


def test_scope_token_frames_components_and_rejects_foreign_children() -> None:
    key = _key()
    bot = key.bot_ref(BotBinding(platform_id="adapter", self_id="account-a"), generation=0)
    other_bot = key.bot_ref(BotBinding(platform_id="adapter", self_id="account-b"), generation=0)
    persona = key.persona_revision(bot, _source(), lifecycle_generation=0)
    session = key.session_ref(bot, "adapter", "umo-1", generation=0)

    assert key.scope_token(bot, persona, session).startswith("scope_v1_")
    with pytest.raises(ValueError, match="^scope parent mismatch$"):
        key.scope_token(other_bot, persona, session)
    assert _frame("é") == b"\x00\x00\x00\x02\xc3\xa9"
    with pytest.raises(ValueError, match="^invalid identity component$"):
        _frame("")


def test_no_adapter_account_proof_provider_has_no_default_authority() -> None:
    assert NoAdapterAccountProofProvider().current("adapter") is None


def test_proven_single_account_rejects_changed_current_account_material() -> None:
    bot = BotRef(token="bot_v1_A", generation=0)
    proof = AdapterAccountProof(
        platform_id="adapter",
        bot_ref=bot,
        proof_generation=4,
        verified_at_ms=100,
        expires_at_ms=200,
        account_set_digest="digest-a",
        account_count=1,
    )

    assert resolve_proven_single_account(
        proof,
        platform_id="adapter",
        current_account_set_digest="digest-a",
        current_proof_generation=4,
        now_ms=150,
    ) == bot
    assert resolve_proven_single_account(
        proof,
        platform_id="adapter",
        current_account_set_digest="digest-b",
        current_proof_generation=4,
        now_ms=150,
    ) is None
    assert resolve_proven_single_account(
        proof,
        platform_id="adapter",
        current_account_set_digest="digest-a",
        current_proof_generation=5,
        now_ms=150,
    ) is None
    assert resolve_proven_single_account(
        proof,
        platform_id="other-adapter",
        current_account_set_digest="digest-a",
        current_proof_generation=4,
        now_ms=150,
    ) is None
    assert resolve_proven_single_account(
        AdapterAccountProof(
            platform_id="adapter",
            bot_ref=bot,
            proof_generation=4,
            verified_at_ms=100,
            expires_at_ms=200,
            account_set_digest="digest-a",
            account_count=2,
        ),
        platform_id="adapter",
        current_account_set_digest="digest-a",
        current_proof_generation=4,
        now_ms=150,
    ) is None
    assert resolve_proven_single_account(
        AdapterAccountProof(
            platform_id="adapter",
            bot_ref=bot,
            proof_generation=4,
            verified_at_ms=151,
            expires_at_ms=200,
            account_set_digest="digest-a",
            account_count=1,
        ),
        platform_id="adapter",
        current_account_set_digest="digest-a",
        current_proof_generation=4,
        now_ms=150,
    ) is None
    assert resolve_proven_single_account(
        proof,
        platform_id="adapter",
        current_account_set_digest="digest-a",
        current_proof_generation=4,
        now_ms=200,
    ) is None


def test_restart_with_no_proof_provider_cannot_reuse_an_old_in_memory_proof() -> None:
    bot = BotRef(token="bot_v1_A", generation=0)
    old_proof = AdapterAccountProof(
        platform_id="adapter",
        bot_ref=bot,
        proof_generation=1,
        verified_at_ms=100,
        expires_at_ms=200,
        account_set_digest="digest-a",
        account_count=1,
    )
    before_restart = CurrentAdapterAccountProof(
        proof=old_proof,
        current_account_set_digest="digest-a",
        current_proof_generation=1,
    )
    after_restart = NoAdapterAccountProofProvider()

    assert before_restart.proof is old_proof
    assert after_restart.current("adapter") is None
    assert resolve_proven_single_account(
        after_restart.current("adapter"),
        platform_id="adapter",
        current_account_set_digest="digest-a",
        current_proof_generation=1,
        now_ms=150,
    ) is None


def test_catalog_history_is_not_an_adapter_account_proof() -> None:
    historical_catalog = {"adapter": "historically-single-account"}
    bot = BotRef(token="bot_v1_A", generation=0)
    adapter_proof = AdapterAccountProof(
        platform_id="adapter",
        bot_ref=bot,
        proof_generation=1,
        verified_at_ms=100,
        expires_at_ms=200,
        account_set_digest="digest-a",
        account_count=1,
    )
    current = CurrentAdapterAccountProof(
        proof=adapter_proof,
        current_account_set_digest="digest-a",
        current_proof_generation=1,
    )

    assert historical_catalog["adapter"] == "historically-single-account"
    assert NoAdapterAccountProofProvider().current("adapter") is None
    assert resolve_proven_single_account(
        None,
        platform_id="adapter",
        current_account_set_digest=current.current_account_set_digest,
        current_proof_generation=current.current_proof_generation,
        now_ms=150,
    ) is None
    assert resolve_proven_single_account(
        current.proof,
        platform_id="adapter",
        current_account_set_digest=current.current_account_set_digest,
        current_proof_generation=current.current_proof_generation,
        now_ms=150,
    ) == bot


def test_v3_bridge_remains_shadow_only_for_scope_v1_authority() -> None:
    assert v3_session_identity.SCOPE_V1_AUTHORITY is False
