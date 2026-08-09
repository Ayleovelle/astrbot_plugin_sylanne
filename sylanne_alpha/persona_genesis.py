"""Fail-closed Persona Genesis activation primitives.

This module deliberately keeps generated persona priors separate from prompts,
conversation text, relationship state, and every session-owned runtime.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import re
import time
from collections.abc import Mapping
from typing import Any

from .provider_routing import (
    ProviderFeature,
    call_text_provider_once,
    resolve_text_provider,
)
from .scope_contracts import PersonaRevisionRef
from .scope_identity import PersonaSource
from .scope_repository import PersonaGenesisLease, ScopeRepository, StaleScopeWrite


PERSONA_GENESIS_PROFILE_KEYS = frozenset(
    {
        "traits_prior",
        "voice_prior",
        "boundary_prior",
        "proactivity_prior",
        "circadian_prior",
    }
)
_FORBIDDEN_SEMANTIC_KEYS = frozenset(
    {
        "memory",
        "relation",
        "relationship",
        "experience",
        "history",
        "user",
        "profile",
        "project",
        "event",
    }
)
_SAFE_TOKEN = re.compile(r"[A-Za-z0-9_.:-]+\Z", re.ASCII)
_SEMANTIC_KEY_PARTS = re.compile(r"[_.:-]+")
_MAX_PROFILE_BYTES = 8192
_MAX_DEPTH = 4
_MAX_NODES = 128
_MAX_CONTAINER_ITEMS = 32
_MAX_TEXT_LENGTH = 64


class PersonaGenesisParseError(ValueError):
    """A provider response is not the closed persona-prior data shape."""


def _reject_constant(_value: str) -> None:
    raise PersonaGenesisParseError("non-finite numeric constant")


def _reject_duplicate_object_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """Build a JSON object only when every input key appeared once."""

    decoded: dict[str, object] = {}
    for key, value in pairs:
        if key in decoded:
            raise PersonaGenesisParseError("profile JSON contains a duplicate key")
        decoded[key] = value
    return decoded


def _safe_string(value: object, *, label: str) -> str:
    if type(value) is not str:
        raise PersonaGenesisParseError(f"{label} must have exact type str")
    if len(value) > _MAX_TEXT_LENGTH or len(value.encode("utf-8")) > _MAX_TEXT_LENGTH:
        raise PersonaGenesisParseError(f"{label} is too long")
    if _SAFE_TOKEN.fullmatch(value) is None:
        raise PersonaGenesisParseError(f"{label} has unsafe characters")
    return value


def _contains_forbidden_semantic_term(value: str) -> bool:
    """Reject whole sensitive terms, including delimiter-compound variants."""

    return any(
        part in _FORBIDDEN_SEMANTIC_KEYS
        for part in _SEMANTIC_KEY_PARTS.split(value.lower())
        if part
    )


def _validate_value(value: object, *, depth: int, nodes: list[int]) -> object:
    nodes[0] += 1
    if nodes[0] > _MAX_NODES:
        raise PersonaGenesisParseError("profile has too many nodes")
    if depth > _MAX_DEPTH:
        raise PersonaGenesisParseError("profile is too deeply nested")

    if type(value) is dict:
        if len(value) > _MAX_CONTAINER_ITEMS:
            raise PersonaGenesisParseError("profile object has too many entries")
        validated: dict[str, object] = {}
        for key, child in value.items():
            safe_key = _safe_string(key, label="profile key")
            if _contains_forbidden_semantic_term(safe_key):
                raise PersonaGenesisParseError("profile contains a forbidden semantic key")
            validated[safe_key] = _validate_value(child, depth=depth + 1, nodes=nodes)
        return validated
    if type(value) is list:
        if len(value) > _MAX_CONTAINER_ITEMS:
            raise PersonaGenesisParseError("profile list has too many entries")
        return [_validate_value(child, depth=depth + 1, nodes=nodes) for child in value]
    if type(value) is str:
        safe_value = _safe_string(value, label="profile string")
        if _contains_forbidden_semantic_term(safe_value):
            raise PersonaGenesisParseError("profile contains a forbidden semantic term")
        return safe_value
    if type(value) is int:
        if not 0 <= value <= 1:
            raise PersonaGenesisParseError("profile number must be finite and in [0, 1]")
        return value
    if type(value) is float:
        if not math.isfinite(value) or not 0.0 <= value <= 1.0:
            raise PersonaGenesisParseError("profile number must be finite and in [0, 1]")
        return value
    raise PersonaGenesisParseError("profile contains an unsupported value type")


def canonical_persona_genesis_json(profile: Mapping[str, object]) -> bytes:
    """Encode a previously validated profile in its sole durable form."""

    if type(profile) is not dict:
        raise PersonaGenesisParseError("profile must be an exact dict")
    try:
        encoded = json.dumps(
            profile,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise PersonaGenesisParseError("profile is not canonical JSON") from exc
    if len(encoded) > _MAX_PROFILE_BYTES:
        raise PersonaGenesisParseError("canonical profile exceeds byte limit")
    return encoded


def parse_persona_genesis_profile(raw: object) -> dict[str, object]:
    """Parse only the exact, bounded five-prior JSON schema.

    The raw provider text is intentionally not retained.  A detached validated
    profile is returned only when it can be encoded into the canonical durable
    representation under the closed safety limits.
    """

    if type(raw) is not str:
        raise PersonaGenesisParseError("provider output must have exact type str")
    try:
        raw_bytes = raw.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise PersonaGenesisParseError("provider output is not UTF-8 encodable") from exc
    if len(raw_bytes) > _MAX_PROFILE_BYTES:
        raise PersonaGenesisParseError("provider output exceeds byte limit")
    try:
        decoded = json.loads(
            raw,
            parse_constant=_reject_constant,
            object_pairs_hook=_reject_duplicate_object_pairs,
        )
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        if isinstance(exc, PersonaGenesisParseError):
            raise
        raise PersonaGenesisParseError("provider output is not JSON") from exc
    if type(decoded) is not dict or set(decoded) != PERSONA_GENESIS_PROFILE_KEYS:
        raise PersonaGenesisParseError("profile must contain exactly the five prior fields")
    for field in PERSONA_GENESIS_PROFILE_KEYS:
        if type(decoded[field]) is not dict:
            raise PersonaGenesisParseError(f"{field} must be an exact object")

    validated = _validate_value(decoded, depth=0, nodes=[0])
    if type(validated) is not dict:  # Defensive only; retained for narrow typing.
        raise PersonaGenesisParseError("profile root is invalid")
    canonical_persona_genesis_json(validated)
    return validated


_GENESIS_ENABLED_KEY = "sylanne_alpha_persona_genesis_enabled"
_GENESIS_PAID_OPT_IN_KEY = "sylanne_alpha_persona_genesis_paid_opt_in"
_GENESIS_PROVIDER_KEY = "sylanne_alpha_persona_genesis_provider_id"
_AUXILIARY_PROVIDER_KEY = "sylanne_alpha_aux_provider_id"
_GENESIS_RESOLUTION_TIMEOUT_SECONDS = 30.0
_GENESIS_PROVIDER_TIMEOUT_SECONDS = 120.0
_GENESIS_RESOLUTION_COOLDOWN_SECONDS = 30.0


class PersonaGenesisOwner:
    """Persona-scoped, single-flight controller for first activation only.

    This owner deliberately has no Session, Relation, Host, memory, or outbox
    capability.  Its only durable boundary is the persona-local repository
    control/activation record.
    """

    def __init__(
        self,
        persona_ref: PersonaRevisionRef,
        *,
        repository: ScopeRepository | None,
        background_tasks: set[Any],
    ) -> None:
        if type(persona_ref) is not PersonaRevisionRef:
            raise ValueError("persona_ref must be a PersonaRevisionRef")
        if repository is not None and type(repository) is not ScopeRepository:
            raise ValueError("repository must be a ScopeRepository or None")
        if type(background_tasks) is not set:
            raise ValueError("background_tasks must be an exact set")
        self._persona_ref = persona_ref
        self._repository = repository
        self._background_tasks = background_tasks
        self._task: asyncio.Task[None] | None = None
        self._task_policy: tuple[object, ...] | None = None
        self._attempt_epoch = 0
        self._retired = False
        self._ready_hint = False
        self._resolve_cooldown_until = 0.0

    def matches_binding(
        self,
        persona_ref: object,
        repository: object,
        background_tasks: object,
    ) -> bool:
        """Return only whether this owner is bound to these exact capabilities."""

        return (
            persona_ref == self._persona_ref
            and repository is self._repository
            and background_tasks is self._background_tasks
        )

    def retire(self) -> None:
        """Synchronously fence this process-local owner and its in-flight task."""

        if self._retired:
            return
        self._retired = True
        self._ready_hint = False
        self._attempt_epoch += 1
        task = self._task
        if task is not None and not task.done():
            task.cancel()

    def invalidate_inflight(self) -> None:
        """Cancel one policy attempt without retiring the Persona lifecycle."""

        self._attempt_epoch += 1
        task = self._task
        if task is not None and not task.done():
            task.cancel()

    def is_ready_cached(self) -> bool:
        """Return the process-local durable-ready hint without taking a file lock."""

        return not self._retired and self._ready_hint

    @staticmethod
    def _gate_enabled(config: object) -> bool:
        return (
            isinstance(config, Mapping)
            and config.get(_GENESIS_ENABLED_KEY) is True
            and config.get(_GENESIS_PAID_OPT_IN_KEY) is True
        )

    @staticmethod
    def _policy_snapshot(config: Mapping[str, Any]) -> tuple[object, ...]:
        return (
            config.get(_GENESIS_ENABLED_KEY),
            config.get(_GENESIS_PAID_OPT_IN_KEY),
            config.get(_GENESIS_PROVIDER_KEY),
            config.get(_AUXILIARY_PROVIDER_KEY),
        )

    def _source_matches(self, source: object) -> bool:
        if type(source) is not PersonaSource:
            return False
        return hashlib.sha256(source.canonical_bytes()).hexdigest() == self._persona_ref.source_fingerprint

    def _active_payload(self) -> dict[str, object] | None:
        if self._retired:
            return None
        repository = self._repository
        if repository is None:
            return None
        try:
            snapshot = repository.read_genesis(self._persona_ref)
        except RepositoryError:
            return None
        if snapshot is None or snapshot.payload.get("state") != "active":
            return None
        return snapshot.payload

    def is_ready(self) -> bool:
        """Whether this exact Persona lifecycle has a durable activation."""

        ready = self._active_payload() is not None
        self._ready_hint = ready
        return ready

    def status(self) -> dict[str, object]:
        """A minimal status projection with the real durable acceptance time."""

        payload = self._active_payload()
        if payload is None:
            return {"state": "awaiting"}
        metadata = payload["safe_metadata"]
        return {
            "state": "active",
            "accepted_at_ms": metadata["accepted_at_ms"],
            "origin_turn_generation": payload["origin_turn_generation"],
        }

    def render_for_turn(self, turn_generation: object) -> str | None:
        """Render only the five durable priors for a later request turn."""

        if self._retired or type(turn_generation) is not int or turn_generation < 0:
            return None
        payload = self._active_payload()
        if payload is None or turn_generation <= payload["origin_turn_generation"]:
            return None
        profile = payload["accepted_profile"]
        if type(profile) is not dict:
            return None
        return "\n".join(
            f"{field}={json.dumps(profile[field], ensure_ascii=False, sort_keys=True, separators=(',', ':'))}"
            for field in (
                "traits_prior",
                "voice_prior",
                "boundary_prior",
                "proactivity_prior",
                "circadian_prior",
            )
        )

    def schedule(
        self,
        source: PersonaSource,
        *,
        config: Mapping[str, Any],
        context: Any,
        origin_turn_generation: int,
    ) -> bool:
        """Start one fire-and-forget activation attempt, or report durable ready.

        There is intentionally no ``persona_ref`` argument: this exact owner is
        permanently bound to the Persona revision that constructed it.
        """

        if not self._gate_enabled(config):
            self.invalidate_inflight()
            return False
        if (
            self._retired
            or type(origin_turn_generation) is not int
            or origin_turn_generation < 0
            or not self._source_matches(source)
            or self._repository is None
        ):
            return False
        policy = self._policy_snapshot(config)
        current = self._task
        if current is not None and not current.done():
            if self._task_policy != policy:
                # A replacement Mapping can leave the old task holding the old
                # object.  Fence that task before it is allowed to write backoff.
                self.invalidate_inflight()
            return False
        try:
            preflight = self._repository.persona_genesis_schedule_preflight_nowait(
                self._persona_ref,
                source_fingerprint=self._persona_ref.source_fingerprint,
            )
        except RepositoryError:
            return False
        if preflight == "active":
            self._ready_hint = True
            return True
        if preflight != "allowed":
            return False
        self._ready_hint = False
        if time.monotonic() < self._resolve_cooldown_until:
            return False
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return False
        attempt_epoch = self._attempt_epoch
        task = loop.create_task(
            self._run(
                source,
                config=config,
                context=context,
                origin_turn_generation=origin_turn_generation,
                policy=policy,
                attempt_epoch=attempt_epoch,
            )
        )
        self._task = task
        self._task_policy = policy
        self._background_tasks.add(task)

        def _consume(done_task: asyncio.Task[None]) -> None:
            self._background_tasks.discard(done_task)
            if self._task is done_task:
                self._task = None
                self._task_policy = None
            try:
                done_task.result()
            except (asyncio.CancelledError, Exception):
                pass

        task.add_done_callback(_consume)
        return False

    def _still_authorized(
        self,
        source: PersonaSource,
        config: Mapping[str, Any],
        policy: tuple[object, ...],
        attempt_epoch: int,
    ) -> bool:
        repository = self._repository
        if (
            self._retired
            or attempt_epoch != self._attempt_epoch
            or not self._gate_enabled(config)
            or self._policy_snapshot(config) != policy
            or not self._source_matches(source)
            or repository is None
        ):
            return False
        try:
            return repository.persona_genesis_authorization_valid(
                self._persona_ref,
                source_fingerprint=self._persona_ref.source_fingerprint,
            )
        except RepositoryError:
            return False

    def _mark_resolution_cooldown(self) -> None:
        self._resolve_cooldown_until = max(
            self._resolve_cooldown_until,
            time.monotonic() + _GENESIS_RESOLUTION_COOLDOWN_SECONDS,
        )

    def _refresh_ready_hint(self) -> None:
        self._ready_hint = self._active_payload() is not None

    @staticmethod
    def _provider_text(result: object) -> str | None:
        if type(result) is str:
            return result
        text = getattr(result, "completion_text", None)
        return text if type(text) is str else None

    @staticmethod
    def _provider_prompt(source: PersonaSource) -> str:
        examples = "\n".join(f"- {dialog}" for dialog in source.begin_dialogs)
        return (
            "Return only one strict JSON object for a persona prior activation. "
            "It must contain exactly traits_prior, voice_prior, boundary_prior, "
            "proactivity_prior, and circadian_prior. Every value must satisfy the "
            "closed JSON schema supplied by the task. Do not include dialogue, users, "
            "memory, relationships, events, provider metadata, or prose.\n"
            "Canonical Persona prompt follows:\n"
            f"{source.prompt}\n"
            "Begin dialogs below are author-expression examples only, not real "
            "experiences, memories, events, or user history:\n"
            f"{examples or '- none'}"
        )

    async def _reject_safely(
        self,
        lease: PersonaGenesisLease | None,
        *,
        source_fingerprint: str,
    ) -> None:
        if lease is None or self._repository is None:
            return
        try:
            if self._repository.reject_persona_genesis_claim(
                self._persona_ref,
                lease,
                source_fingerprint=source_fingerprint,
            ):
                return
        except RepositoryError:
            pass
        try:
            # A stale Persona record must never release a replacement lease; the
            # repository compares both ID and fence before clearing this slot.
            self._repository.release_persona_genesis_lease(lease)
        except RepositoryError:
            return

    async def _release_stale_lease(self, lease: PersonaGenesisLease | None) -> None:
        """Discard a stale result without changing its Persona-local claim."""

        if lease is None or self._repository is None:
            return
        try:
            # The repository compares both lease ID and fence, so this cannot
            # clear a later caller's global slot.
            self._repository.release_persona_genesis_lease(lease)
        except RepositoryError:
            return

    async def _run(
        self,
        source: PersonaSource,
        *,
        config: Mapping[str, Any],
        context: Any,
        origin_turn_generation: int,
        policy: tuple[object, ...],
        attempt_epoch: int,
    ) -> None:
        repository = self._repository
        if repository is None:
            return
        lease: PersonaGenesisLease | None = None
        try:
            if not self._still_authorized(source, config, policy, attempt_epoch):
                return
            # The front path performed a zero-wait preflight.  Repeat it under
            # the ordinary durable lock before any provider lookup or budget use.
            if not repository.persona_genesis_schedule_allowed(
                self._persona_ref,
                source_fingerprint=self._persona_ref.source_fingerprint,
            ):
                self._refresh_ready_hint()
                return
            with repository.persona_genesis_provider_slot() as has_slot:
                if not has_slot or not self._still_authorized(
                    source,
                    config,
                    policy,
                    attempt_epoch,
                ):
                    return
                if not repository.persona_genesis_schedule_allowed(
                    self._persona_ref,
                    source_fingerprint=self._persona_ref.source_fingerprint,
                ):
                    self._refresh_ready_hint()
                    return
                try:
                    resolution = await asyncio.wait_for(
                        resolve_text_provider(
                            feature=ProviderFeature.GENESIS,
                            config=config,
                            context=context,
                            umo=None,
                        ),
                        timeout=_GENESIS_RESOLUTION_TIMEOUT_SECONDS,
                    )
                except Exception:
                    # Resolution never claims a durable lease or consumes the
                    # daily budget.  A local cooldown prevents request storms.
                    self._mark_resolution_cooldown()
                    return
                if (
                    getattr(resolution, "provider", None) is None
                    or getattr(resolution, "explicit_invalid", False)
                    or not self._still_authorized(source, config, policy, attempt_epoch)
                ):
                    if getattr(resolution, "provider", None) is None or getattr(
                        resolution,
                        "explicit_invalid",
                        False,
                    ):
                        self._mark_resolution_cooldown()
                    return
                lease = repository.claim_persona_genesis(
                    self._persona_ref,
                    source_fingerprint=self._persona_ref.source_fingerprint,
                    origin_turn_generation=origin_turn_generation,
                )
                if lease is None:
                    return
                if not self._still_authorized(source, config, policy, attempt_epoch):
                    await self._release_stale_lease(lease)
                    return
                result = await asyncio.wait_for(
                    call_text_provider_once(
                        resolution.provider,
                        prompt=self._provider_prompt(source),
                        max_tokens=800,
                        temperature=0.1,
                    ),
                    timeout=_GENESIS_PROVIDER_TIMEOUT_SECONDS,
                )
                if not self._still_authorized(source, config, policy, attempt_epoch):
                    await self._release_stale_lease(lease)
                    return
                raw = self._provider_text(result)
                if raw is None:
                    await self._reject_safely(
                        lease,
                        source_fingerprint=self._persona_ref.source_fingerprint,
                    )
                    return
                profile = parse_persona_genesis_profile(raw)
                if not self._still_authorized(source, config, policy, attempt_epoch):
                    await self._release_stale_lease(lease)
                    return
                repository.commit_persona_genesis_activation(
                    self._persona_ref,
                    lease,
                    profile=profile,
                    source_fingerprint=self._persona_ref.source_fingerprint,
                    origin_turn_generation=origin_turn_generation,
                )
                self._ready_hint = True
                lease = None
        except asyncio.CancelledError:
            if self._still_authorized(source, config, policy, attempt_epoch):
                await self._reject_safely(
                    lease,
                    source_fingerprint=self._persona_ref.source_fingerprint,
                )
            else:
                await self._release_stale_lease(lease)
            raise
        except (Exception,):
            if self._still_authorized(source, config, policy, attempt_epoch):
                await self._reject_safely(
                    lease,
                    source_fingerprint=self._persona_ref.source_fingerprint,
                )
            else:
                await self._release_stale_lease(lease)


RepositoryError = (OSError, RuntimeError, StaleScopeWrite, ValueError)


__all__ = [
    "PERSONA_GENESIS_PROFILE_KEYS",
    "PersonaGenesisParseError",
    "PersonaGenesisOwner",
    "canonical_persona_genesis_json",
    "parse_persona_genesis_profile",
]
