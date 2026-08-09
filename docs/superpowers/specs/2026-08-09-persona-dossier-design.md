# Persona dossier design

## Status and routing

This implements the already-approved Task 15 card: a read-only Persona dossier
opened from each Personality card.  It is intentionally not a new route in the
Vue application and it does not add a mutable Persona workflow.

DevKit routing inputs: one coherent write scope spanning the scoped API, the
exact-scope store/client, and the Personality view; high privacy/isolation risk;
one writer; moderate interface ambiguity; focused Python and Vitest verification
available.  The Fast Lane compiler has no trusted host lease in this recovery
session, so it correctly admits no worker dispatch.  The coordinator owns the
single fenced write scope and will not manufacture a parallel lease.

## User-visible behavior

- Each of the three existing Personality cards is keyboard-activatable and
  opens the same modal dossier.
- The dossier is selected by the current Bot + Persona only.  Changing only the
  Session neither redirects nor closes a dossier request.
- Closing the modal, changing Bot/Persona, or changing that Persona lifecycle
  generation aborts/invalidates the request and clears any displayed snapshot.
- The modal contains no write controls and never uses the observation visual
  variant or terminology.

## API contract

Add one authenticated, read-only endpoint to both hosts:

```
GET /api/v1/bots/{bot_ref}/personas/{persona_ref}/dossier
```

This is deliberately outside the session-owned scoped root.  It must not mint,
accept, or infer a Session nonce.  The endpoint resolves only the exact active
Bot and Persona from durable manifests, then reads the already-validated
Persona Genesis record.  It never calls PersonaManager, creates runtime state,
or chooses a session as a fallback.

Success is a closed DTO:

```
{
  "ok": true,
  "persona_scope": { "bot_ref": "opaque", "persona_ref": "opaque" },
  "generations": { "bot": 0, "persona_lifecycle": 0 },
  "persona": {
    "display": "Persona …",
    "ref_short": "…",
    "fingerprint_short": "…",
    "resolution": "active",
    "genesis": {
      "state": "active | awaiting",
      "priors": { "five bounded Genesis priors only" },
      "growth_enabled": true,
      "accepted_at_ms": 0
    },
    "updated_at_ms": 0
  }
}
```

`priors`, `growth_enabled`, and `accepted_at_ms` are present only for an active
Genesis record.  A claimed, backed-off, absent, malformed, or stale record is
projected only as `genesis.state = "awaiting"`; provider control fields are
never exposed.  `display` and both short codes are derived from opaque durable
references, not from a Persona source.  The path echo exists only to fence a
client response; it is not a raw Bot identity.

Unknown, retired, or stale Persona paths are non-enumerating `404` responses.
Malformed paths are `400`, repository failures are `503`, and legacy
`?session=` selectors are rejected with `400`.  Authentication remains the
existing standalone/AstrBot host authentication.

## Frontend fencing

The scope store gains a Persona-only snapshot containing Bot ref, Persona ref,
Bot generation, Persona lifecycle generation, and a `personaEpoch`.  It is
valid only when every catalog entry for that Bot+Persona agrees on those parent
generations.  `personaEpoch` changes for Bot/Persona or their parent generation
only; the existing full `selectionEpoch` continues to change for Session work.

The client builds the exact two-level path and performs a normal authenticated
GET.  For standalone fetch it passes an AbortSignal.  AstrBot Pages cannot
preserve AbortSignal semantics, so an abort still clears local state and the
same response-fence rejects any late bridge response.

The response is accepted only when the exact two-token echo, Bot generation,
Persona lifecycle generation, and `personaEpoch` all still match.  No global
"current session" value participates in that check.

## Component boundary

`PersonalityView` owns opening, request lifecycle, stale rejection, and
clearing.  A new `components/persona/PersonaDossier.vue` is a presentational
modal using the standard dialog shell.  It renders identity, bounded Genesis
priors, growth state, and timestamps only.  It accepts no user input.

## Verification

- Add backend redline tests for the exact DTO, no source/prompt/session/runtime
  leakage, active/awaiting projection, lifecycle fence, 404/400 behavior, and
  both host adapters.
- Add store/client tests for a Persona-only snapshot, stale reply rejection,
  and Session-only selection stability.
- Add a dossier source/interaction test: all three cards use `interactive` and
  `@activate`; click, Enter, and Space open it; close/scope changes clear it;
  it contains no input, textarea, observation marker, or write endpoint.
- Run focused Python and Vitest tests, then the frontend suite/build, static
  syntax checks, and `git diff --check` before acceptance.
