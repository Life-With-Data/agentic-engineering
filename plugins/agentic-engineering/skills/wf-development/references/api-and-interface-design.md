# API and Interface Design

Design stable, well-documented interfaces that are hard to misuse — REST
APIs, GraphQL schemas, module boundaries, component props, any surface where
one piece of code talks to another.

## Positioning

This is **design-time contract authoring** — shaping an interface before it
exists. Two review-time agents inspect interfaces after the code is written:
`architecture-strategist` (pattern compliance, structural integrity) and
`integration-boundary-reviewer` (untested external-boundary calls). Author
here; review there.

## Core principles

- **Hyrum's Law.** With enough users, every observable behavior — documented
  or not, including error text, timing, and ordering — becomes a de facto
  contract. Be intentional about what the interface exposes; don't leak
  implementation details; plan deprecation at design time (additive changes,
  versioned removals, a migration path off deprecated fields). When a
  contract change forces a data-layer migration, hand it to the
  `data-migration-expert` agent. Tests are not enough — "safe" changes can
  break users who depend on undocumented behavior.
- **One-version rule.** Never force consumers to choose between versions of
  the same thing; extend rather than fork.
- **Contract first.** Define the interface (types, error semantics,
  idempotency) before implementing; the contract is the spec.
- **Consistent error semantics.** One error strategy everywhere: a stable
  machine-readable code, a human-readable message, correct status semantics
  (400 invalid / 401 unauthenticated / 403 unauthorized / 404 missing /
  409 conflict / 422 validation / 5xx server).
- **Validate at boundaries.** Parse and validate at the edge; hand typed,
  trusted data inward.
- **Prefer addition over modification.** New optional fields and new
  endpoints over changed meanings; breaking changes get a version and a
  migration path.
- **Predictable naming.** Consistent casing, plural resource nouns, no
  synonyms for the same concept across the surface.

## Surface-specific notes

- REST: resources are nouns, verbs come from methods; paginate every
  collection endpoint from day one (cursor-based when ordering matters);
  PATCH means partial update with only provided fields changing; DELETE is
  idempotent.
- Typed languages: discriminated unions for variants rather than optional
  fields that are "sometimes present"; separate input types from output
  types; branded/opaque ID types where mixing IDs is a real hazard.

Framework- and language-specific idioms come from the repository's mapped
assets, not this reference.

## Red flags

Endpoints that leak database schema directly; error responses with different
shapes across endpoints; unpaginated collections; boolean parameters that
change an endpoint's meaning; interfaces that require call-order knowledge to
use safely; "temporary" breaking changes. And the rationalizations: "we'll
version it later", "nobody depends on that behavior" (Hyrum says they do),
"it's internal" (internal interfaces have consumers too).

## Verification

- The contract is written and reviewed before implementation.
- Errors follow the one house shape; every failure path has a stable code.
- Collections paginate; mutations are idempotent where retries can happen.
- Nothing observable leaks that the contract doesn't intend to commit to.
