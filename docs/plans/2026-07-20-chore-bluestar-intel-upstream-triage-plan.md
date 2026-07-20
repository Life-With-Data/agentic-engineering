---
title: "chore: resolve the aagnone3/bluestar-intel upstream-scan triage"
type: chore
date: 2026-07-20
origin: docs/brainstorms/2026-07-20-bluestar-intel-upstream-triage-brainstorm.md
github_issue: 225
---

# chore: resolve the `aagnone3/bluestar-intel` upstream-scan triage

## Overview

Issue [#225](https://github.com/Life-With-Data/agentic-engineering/issues/225) is an adoption-triage
report for the source `aagnone3/bluestar-intel`, captured manually from the cross-repo analysis
merged in [PR #223](https://github.com/Life-With-Data/agentic-engineering/pull/223). Per the triage
contract in [`docs/upstream-sources.md`](../upstream-sources.md), *a scan issue is resolved by a
triage PR* — this plan is that resolution, in three sequenced PRs:

1. **Maiden triage** (docs-only): register the source and file a verdict for every candidate.
2. **Adopt `skill/authenticated-browser-sessions`** as a new, provider-agnostic skill.
3. **Fold `skill/validation`'s routing table into the existing `verification-loop` skill.**

## Problem Statement / Motivation

Three problems, in descending order of importance:

**1. An unregistered source is an unguarded source.** `aagnone3/bluestar-intel` has no entry in
`docs/upstream-sources.md`, so `tests/upstream-registry.test.ts` has nothing to lint, the license
and visibility are unrecorded, and #225 is maintained by hand instead of by the scanner. The
registry is the single ledger; a source outside it is provenance debt.

**2. Both `test-browser` and `agent-browser` dead-end at a sign-in wall.** Verified by reading them:

- `test-browser` (`skills/test-browser/SKILL.md`, "Human Verification (When Required)") pauses and
  asks a human — its table literally routes OAuth to *"Please sign in with [provider] and confirm it
  works"*.
- `agent-browser` (`skills/agent-browser/SKILL.md`, "Login Flow") types literal credentials into the
  page (`agent-browser fill @e2 "password123"`). For a real account that is prohibited by this
  repo's operating rules, and there is no auth-wall guidance anywhere in the file.

Candidate 1 closes exactly this gap **without ever handling a password**: mint a session
server-side via the auth provider's backend API, redeem a single-use ticket in-page, and use
dedicated test users.

**3. `verification-loop` has no change-type routing.** Verified: 122 lines, six fixed phases always
run in the same order, the only conditionality being "stop on a build/type failure" and per-phase
N/A skipping; it delegates to no component skill. Candidate 2's contribution is precisely the
missing piece — a table mapping *what changed* → *which checks, in what order*, with a Quick/Thorough
split.

## Proposed Solution

Follow the shape every prior maiden triage in this repo already took (PRs #33, #98, #108, #109):
**a docs-only triage PR touching exactly two files** — a new
`docs/upstream-reports/2026-07-20-bluestar-intel-initial-triage.md` plus an append to
`docs/upstream-sources.md` — and then **separate adoption PRs**, each re-pinning its registry line
from `deferred:` to `adopted:` once the adopting PR number exists.

That ordering is forced, not stylistic: the registry lint requires every `adopted:` entry to match
`(upstream: <path>@<sha>, adapted|verbatim) — PR #NN — @who YYYY-MM-DD`, and `#NN` cannot be written
before the PR exists. Precedent for the two-step pin: commits `09895022`, `d8cb4301`, `33472c8d`,
`d7837696`, each a one-line registry edit after the adoption merged.

### Verified facts this plan is built on

| Fact | Value | How verified |
|---|---|---|
| Canonical repo | `Life-With-Data/bluestar-intel` (`aagnone3/bluestar-intel` redirects) | `gh api repos/aagnone3/bluestar-intel` |
| Visibility / license | private / none | same call — `licenseInfo: null` |
| HEAD sha (`main`) | `f20f4c8c9c2ee84aee25d9c7d356bfd51a16ee14` | `gh api .../commits/main` |
| Candidate 1 path | `.claude/skills/authenticated-browser-sessions/SKILL.md` (17,490 bytes) | contents API |
| Candidate 2 path | `.claude/skills/validation/SKILL.md` (4,181 bytes) | contents API |
| Other skills at that sha | `cdk-infrastructure`, `dagster-data-pipelines`, `server-patterns`, `visual-validation` | contents API |

The last row is why a bulk-deferral baseline is mandatory in PR 1: without
`all-unlisted @ f20f4c8c…`, the next triage of this source re-surfaces its whole inventory.

## Technical Considerations

- **Slug form.** Register as `aagnone3/bluestar-intel`, matching the sibling `aagnone3/agent-leverage`
  entry (also pre-transfer). The lint only requires `repo:` to equal `https://github.com/<slug>`;
  consistency with the neighbouring entry beats a one-off correction. A slug migration across all
  entries is its own change.
- **License line.** `unlicensed-private (verified 2026-07-20)` — the exact form already used for
  `aagnone3/agent-leverage`. The source is first-party (Life-With-Data org).
- **`scan: manual-only`** — private source, consistent with the sibling entry, and the mode the
  issue's own ready-to-paste block specifies.
- **Private-source disclosure is bounded.** Both candidates' details are already public via merged
  PR #223, so naming them discloses nothing new. Nothing else from this source may be described in
  the public registry beyond the bulk-deferral line.
- **`verification-loop` is itself adopted** (from `affaan-m/ECC`, PR #61). Folding candidate 2 into
  it layers a second source into one skill — legal, but the provenance must stay legible: the
  `bluestar-intel` entry records `skill/validation … adapted into skills/verification-loop`.
- **Do not overwrite #225's body.** `/workflows-plan` Step 7 normally rewrites the parent issue body
  from the plan. Here the parent *is* the scan report, whose own body says discussion belongs in
  comments and whose generator says never to hand-edit it. This plan therefore links from a comment
  and leaves the body intact; the `github_issue: 225` frontmatter above is the join key.

## System-Wide Impact

- **Interaction graph.** PR 1 touches docs only — the blast radius is
  `tests/upstream-registry.test.ts` and `tests/dependency-policy.test.ts`. PRs 2–3 add/modify a skill,
  which cascades into `plugin.json` + `marketplace.json` descriptions, both READMEs, and the
  generated docs site (`bun run docs:build` / `docs:check`), all enforced by
  `tests/plugin-consistency.test.ts`.
- **API surface parity.** Adding candidate 1 means three browser-adjacent skills must cross-reference
  coherently: `test-browser` (human-in-the-loop), `agent-browser` (driving), and the new auth
  companion. Each of the first two needs a pointer at its auth wall, or the new skill will not be
  found at the moment it is needed.
- **State lifecycle risks.** None persistent — this is documentation and prompt content.
- **Error propagation.** The only failure mode that matters is a half-filed registry: an adoption
  merged while its entry still reads `deferred:`. The two-step pin makes that state legal but
  short-lived; each adoption sub-issue owns closing it.
- **Integration scenarios.** (a) `bun test` after PR 1 with a deliberately malformed entry must fail
  on the grammar assertion; (b) `bun run docs:check` after PRs 2–3 must be clean.

## External System Wiring

**No external wiring required** for this work item. Note that the *adopted skill itself* documents
external wiring for its users (an auth provider's backend API key and test-user convention); that is
content inside the skill, not configuration this repo must provision.

## Acceptance Criteria

- [ ] `docs/upstream-sources.md` contains an `aagnone3/bluestar-intel` section with `repo:`,
      `license:`, `visibility: private`, `scan: manual-only`, `adopted:`, `deferred:`.
- [ ] Both reported candidates carry a filed verdict — no candidate left "reported but unresolved".
- [ ] A bulk-deferral line `all-unlisted @ f20f4c8c9c2ee84aee25d9c7d356bfd51a16ee14` covers the rest
      of the source tree.
- [ ] `docs/upstream-reports/2026-07-20-bluestar-intel-initial-triage.md` exists and records the
      per-candidate evidence and verdict.
- [ ] A provider-agnostic `authenticated-browser-sessions` skill exists, with Clerk as the worked
      example, and `test-browser` + `agent-browser` each point at it from their auth wall.
- [ ] `verification-loop` gains a change-type routing table with a Quick/Thorough split, delegating
      to its existing phases plus `test-browser` / `agent-browser`.
- [ ] Every adopted component's registry line is pinned to its adopting PR number and the upstream
      `<path>@<sha>`, marked `adapted`.
- [ ] Component counts agree across `plugin.json`, `marketplace.json`, both READMEs, and the docs
      site; `bun test` and `bun run docs:check` are green.
- [ ] Each adopting commit carries an `Upstream-Ref:` trailer.
- [ ] Issue #225's body is unmodified (the plan is linked by comment).

## Validation

- **Automated:** `bun test` (covers `upstream-registry`, `dependency-policy`, `plugin-consistency`,
  `conversion-policy`) and `bun run docs:check`. After PR 1, `bun test tests/upstream-registry.test.ts`
  must pass with the new entry present.
- **Grammar spot-check:** every new registry entry ends with ` — @who YYYY-MM-DD`; every `adopted:`
  entry matches `\(upstream: \S+@[0-9a-f]{7,40}, (adapted|verbatim)\)`.
- **Manual:** re-read the adopted `authenticated-browser-sessions` skill against its upstream source
  and confirm it was *adapted* (local conventions, provider-neutral) and not pasted — this is the
  supply-chain review, and it is a human's job.
- **Rollback:** each PR is independently revertible; reverting an adoption also requires reverting
  its registry pin line so the ledger does not claim an adoption that no longer exists.

## Success Metrics

- #225 closes with zero candidates in an unresolved state.
- A future scan of this source (manual) reports **0 new candidates** at the same sha — proof the
  bulk-deferral baseline works.
- An agent hitting a sign-in wall in `test-browser`/`agent-browser` finds the auth companion from
  the skill it is already in.

## Dependencies & Risks

| Risk | Mitigation |
|---|---|
| **Upstream prompt injection** — both candidates are agent prompts from a private repo. | Read the bodies only inside a credential-free subagent, treat as untrusted data, adapt-never-copy, and rely on human review of the adopting PR as the security boundary. Bodies were deliberately **not** read during grooming. |
| Adoption merges while its registry line still says `deferred:`. | The pin step is part of the same sub-issue's Definition of Done, not a follow-up wish. |
| The folded routing table bloats `verification-loop` past usefulness. | Keep it a table plus a Quick/Thorough note. If it outgrows a section, promote it to a thin standalone `validation` skill — the alternative recorded in the brainstorm. |
| Adding a skill silently breaks counts. | `bun test` is the gate; run before committing, per root `CLAUDE.md`. |
| Sibling scan issues #226 / #227 overlap this source's candidates. | Out of scope here; each is its own work item. Check for duplicate candidate IDs at adoption time. |

## Sources & References

- **Origin brainstorm:** [docs/brainstorms/2026-07-20-bluestar-intel-upstream-triage-brainstorm.md](../brainstorms/2026-07-20-bluestar-intel-upstream-triage-brainstorm.md)
  — decisions carried forward: staged triage-then-adopt; fold candidate 2 into `verification-loop`
  rather than create a 65th skill; register under the `aagnone3/` slug for consistency.
- Triage contract + entry grammar: [`docs/upstream-sources.md`](../upstream-sources.md) (SCHEMA comment)
- [`docs/dependency-policy.md`](../dependency-policy.md) — adopt vs depend tracks
- Precedent triage PRs: #33 (ECC), #98 (addyosmani), #108 (superpowers), #109 (mattpocock)
- Precedent registry-pin commits: `09895022`, `d8cb4301`, `33472c8d`, `d7837696`
- Scan report issue: #225 · captured from PR #223
