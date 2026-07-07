# External Dependency Policy

How this marketplace consumes work from other repositories. Two tracks exist;
every external source uses exactly one track per upstream plugin, and both
tracks share one trust ledger: `docs/upstream-sources.md`.

Enforced by `tests/dependency-policy.test.ts` (mechanical invariants) and
`tests/upstream-registry.test.ts` (registry grammar). This document is the
human-readable rationale; the tests are the source of enforcement.

## Track A — Adopt (import individual components)

Copy a specific agent/command/skill/hook into this repo, adapted to local
conventions. This is the existing `/upstream-scan` → triage → adoption pipeline
defined in `docs/upstream-sources.md` (provenance pinning, supply-chain review,
human-reviewed PRs). Nothing changes.

**Use when:** we want a handful of components, adaptation adds value, or the
upstream is unmaintained. Default track for case-by-case imports.

## Track B — Depend (formal plugin dependency)

Declare another plugin in a local plugin's `.claude-plugin/plugin.json`
`dependencies` array. Claude Code auto-installs it, enables it transitively,
and surfaces breakage in `/doctor` (requires Claude Code ≥ v2.1.110; enable/
disable semantics ≥ v2.1.143).

**Use when:** we want a whole plugin's surface as-is from an actively
maintained upstream, and adapting would only create a fork to babysit.

Mechanics:

- **Cross-marketplace deps** require the target marketplace's name in
  `allowCrossMarketplaceDependenciesOn` in the root `marketplace.json`.
- **Versioned** (`{ "name": ..., "version": "~x.y.z" }`) only when the
  upstream tags releases as `{plugin-name}--v{version}`; a constraint against
  an untagged repo fails with `no-matching-tag`.
- **Unversioned** (bare name) when the upstream does not tag. The dep then
  tracks the upstream's latest, so its registry entry MUST have `scan: auto` —
  `/upstream-scan` drift monitoring is the compensating control for the
  missing version pin. Versioned deps may be `manual-only` (the constraint
  holds them).

## Cohesion invariants (how the tracks don't conflict)

1. **One ledger.** Every external source — adopt-track or depend-track — has a
   registry entry in `docs/upstream-sources.md`. Depend-track sources add a
   `dependency:` line (grammar in the registry schema comment). A dependency
   with no registry entry, or an allowlist entry with no dependency, fails CI.

2. **Mutual exclusion per upstream plugin.** A given upstream plugin is
   consumed by exactly one track. Declaring a dependency on plugin X
   forecloses adopting components from X's directory; the PR adding the
   dependency deletes any previously adopted copies from X (prefer deletion —
   no shadowed, diverging duplicates). Multi-plugin upstream repos are split
   per plugin: depending on `marketing` from a repo does not block adopting
   from that repo's `sales/`.

3. **Promotion / demotion.** Recurring sync churn across ≥3 adoptions from one
   upstream plugin → evaluate promoting to a dependency. A dependency used for
   a single component → demote to adoption and drop the dep. Either direction
   lands in one PR that restores invariant 2.

4. **Allowlist is the trust gate.** Adding a marketplace to
   `allowCrossMarketplaceDependenciesOn` requires a completed source
   evaluation (`/analyze-source` or an upstream-scan triage) recorded in the
   registry. No standing trust: the allowlist may only name marketplaces some
   local plugin actually depends on.

5. **The core plugin stays dependency-free.** `plugins/agentic-engineering` is
   engineering-specific and universally installed; it declares no
   `dependencies`. Cross-plugin composition lives in thin domain plugins
   (e.g., a future `marketing-stack`) that hold the orchestrator skills plus
   the `dependencies` array, typically with `defaultEnabled: false`.

6. **Namespaces.** Dependency-provided skills keep their upstream plugin
   namespace; adopted components live under ours. No local component may
   shadow a dependency's skill name.

## Installing plugins with dependencies

Claude Code resolves dependencies only from marketplaces the user has already
added; it will not add a remote marketplace on its own (the error prints the
`claude plugin marketplace add` command). Any local plugin that declares
cross-marketplace dependencies must state the one-line marketplace-add
prerequisite in its README.

## Our own releases

We tag our plugins with `claude plugin tag --push` (`{plugin-name}--v{version}`)
so downstream consumers can pin us with semver constraints.
