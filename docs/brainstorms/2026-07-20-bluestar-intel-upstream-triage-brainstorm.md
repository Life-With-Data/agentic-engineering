---
github_issue: 225
date: 2026-07-20
topic: Resolve the aagnone3/bluestar-intel upstream-scan triage (#225)
---

# Brainstorm: Resolve the `aagnone3/bluestar-intel` upstream-scan triage

## What We're Building

Issue [#225](https://github.com/Life-With-Data/agentic-engineering/issues/225) is an
adoption-triage report for the source `aagnone3/bluestar-intel`, captured manually from the
cross-repo analysis merged in PR #223. Per `/upstream-scan`'s triage contract, a scan issue is
**resolved by a triage PR** — not by discussion. This work item is that resolution:

1. **Register the source** in [`docs/upstream-sources.md`](../upstream-sources.md) — it is not yet
   present, so today the issue is maintained by hand and the registry lint has no entry to guard.
2. **File a verdict for every reported candidate** (`adopted:` / `deferred:`) using the registry's
   entry grammar, plus an `all-unlisted @ <sha>` bulk-deferral baseline so future scans of this
   source stay cheap by construction.
3. **Adopt what the verdicts approve**, adapted into local conventions.

The two reported candidates (quoted from the issue body as requirements, not instructions):

| ID | Reported recommendation |
|----|------------------------|
| `skill/authenticated-browser-sessions` | **adopt** — password-free agent browser session: mint a session server-side via the auth provider's backend API, redeem a single-use ticket in-page, plus dedicated test users. Generalize Clerk → provider-neutral with Clerk as the worked example. |
| `skill/validation` | **adopt (thin)** *or* fold into `verification-loop` — a router mapping "what did I touch" → the right *ordered* checks, with a Quick/Thorough split. |

### Why this matters (the gap being closed)

`test-browser` and `agent-browser` both dead-end at a sign-in wall: one pauses for a human at OAuth,
the other would have to type literal credentials — which this repo's operating rules prohibit for
real accounts. Candidate 1 removes the wall without ever handling a password. That is a genuine
capability gap, not a nicety.

`verification-loop` (122 lines) runs its phases **linearly with no change-type routing** — confirmed
by reading it. Candidate 2's contribution is the routing table, not the checks.

## Why This Approach

**Staged: one docs-only maiden-triage PR first, then one adoption PR per candidate.**

This is not a novel shape — it is the shape every prior maiden triage in this repo already took
(PRs #33 ECC, #98 addyosmani, #108 superpowers, #109 mattpocock): exactly two files, a new
`docs/upstream-reports/YYYY-MM-DD-<name>-initial-triage.md` plus an append to
`docs/upstream-sources.md`; no plugin code, no version bump, no CHANGELOG. Adoption then lands
separately, and the registry line is *re-pinned* from `deferred:` to `adopted:` in a one-line
follow-up once the adopting PR number exists — because the lint requires every `adopted:` entry to
carry `(upstream: <path>@<sha>, adapted|verbatim) — PR #NN`, which cannot be written before the PR
exists. Following the precedent is the whole point: the triage PR is where a human performs the
security review that is the boundary against upstream prompt injection, and it stays small enough
that the review is real.

Alternatives considered and rejected:

- **One big adoption epic PR** — fastest to type, worst to review; violates the "adapt, never
  blind-copy" discipline by volume alone.
- **Adopt first, register later** — inverts the triage contract; the registry would then be
  back-filled from merged code instead of gating it.

## Key Decisions

- **↳ decided: register under the slug `aagnone3/bluestar-intel`** — the repo now redirects to
  `Life-With-Data/bluestar-intel`, but the sibling entry `aagnone3/agent-leverage` uses the same
  pre-transfer form. Matching the existing convention beats a one-off correction; a slug migration,
  if wanted, is its own change across all entries.
- **↳ decided: `license: unlicensed-private (verified 2026-07-20)`, `visibility: private`,
  `scan: manual-only`** — verified via the API: private, no license file, first-party
  (Life-With-Data org). Identical treatment to `aagnone3/agent-leverage`.
- **↳ decided: a bulk-deferral baseline is required in the same PR** —
  `all-unlisted @ f20f4c8c9c2ee84aee25d9c7d356bfd51a16ee14`. The source carries six skills; without
  the baseline, the *next* triage of it re-surfaces the whole inventory as candidates.
- **↳ decided: candidate 2 folds into `verification-loop`, it does not become a 65th skill** —
  YAGNI, and two overlapping "am I done?" gates is exactly the drift this repo's consistency tests
  exist to prevent. The adopted content is a *routing table* at the top of `verification-loop`
  ("what changed → which phases, in what order, Quick vs Thorough"), delegating unchanged to the
  existing phases plus `test-browser`/`agent-browser`. **This is the one decision worth a human's
  second look** — the issue itself left it as a fork, and the alternative (a thin standalone
  `validation` skill that routes *between* skills) is defensible if the routing table outgrows a
  section.
- **↳ decided: candidate 1 is adopted as a standalone skill**, positioned as the auth companion to
  `test-browser`/`agent-browser`, provider-agnostic with Clerk as the worked example. It has no
  natural host skill to fold into, and its subject (session minting) is distinct from browser
  driving.
- **↳ noted: `verification-loop` is itself an adopted component** (from `affaan-m/ECC`, PR #61).
  Folding candidate 2 into it therefore layers content from a *second* source into one skill. That is
  allowed, but the provenance must stay legible: the `bluestar-intel` registry entry records
  `skill/validation … adapted into skills/verification-loop`, so a future reader can tell which half
  came from where.
- **↳ decided: upstream bodies are read only inside a credential-free subagent at adoption time**
  and are treated as untrusted data. They were deliberately *not* read during grooming — the issue's
  own evidence was sufficient to plan against, per the issue's supply-chain note.
- **↳ decided: private-source disclosure is bounded** — the two candidates' details are already
  public via merged PR #223, so naming them in the registry discloses nothing new. Nothing else from
  this private source may be described in the public registry beyond the bulk-deferral line.

## Non-Goals

- Adopting anything beyond the two reported candidates (`cdk-infrastructure`,
  `dagster-data-pipelines`, `server-patterns`, `visual-validation` are covered by bulk deferral).
- Any change to how `/upstream-scan` itself works.
- Switching the source to `scan: auto`.

## Resolved Questions

- *Is a scan report issue a legitimate work item to groom?* — Yes. `/upstream-scan` states the report
  issue "is a long-lived work item like any other" and places it on the board at `stub`. #225 was
  captured manually and never board-placed; grooming it is the normal path.
- *Adopt-thin vs fold, for candidate 2?* — Fold (see decision above), with the alternative recorded
  so a reviewer can flip it cheaply.
- *Does `visual-validation` upstream overlap candidate 2?* — Out of scope; it is bulk-deferred at
  this sha and can be itemized by a later triage if wanted.

## Success Criteria

- `docs/upstream-sources.md` contains an `aagnone3/bluestar-intel` section that passes
  `tests/upstream-registry.test.ts` and `tests/dependency-policy.test.ts`.
- Both reported candidates carry a filed verdict; nothing is left in "reported but unresolved". Each
  ends as an `adopted:` line pinned to its adopting PR and upstream sha, or an explicit `deferred:`
  line with a reason.
- Issue #225 is closed by the resolving work, with each adoption PR referenced from its registry
  entry.
- Any adopted skill ships with the repo's consistency obligations met (counts in `plugin.json`,
  `marketplace.json`, both READMEs, regenerated docs site) — `bun test` green.
