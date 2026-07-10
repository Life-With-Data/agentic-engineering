# Cross-Repo Operational-Tool Integration Opportunities

> **Scope:** A triage of the Claude operational tooling (hooks, skills, commands,
> agents) across three sibling repositories against the `agentic-engineering`
> marketplace, to find components worth adopting into the core plugin.
>
> **Sources scanned** (all first-party, all **private**):
> `aagnone3/agent-toolkit`, `aagnone3/agent-leverage`, `aagnone3/bluestar-intel`.
>
> **Status:** Plan / recommendation only — no component is imported by this PR.
> Adoption stays a deliberate, human-reviewed act through the existing
> `/upstream-scan` → triage pipeline (`docs/upstream-sources.md`,
> `docs/dependency-policy.md`).

## Why plan-only (the governance boundary)

Two constraints shape the recommendation and are the reason this PR imports
nothing:

1. **The sources are private; this marketplace is public.** The registry's own
   PRIVATE SOURCES rule says entries "must not disclose non-public component
   details." Committing the sibling repos' full internal inventories into the
   schema-linted `docs/upstream-sources.md` (a public file) would do exactly
   that. Registering them is a maintainer call, not an autonomous one.
2. **Adopt, never blind-copy.** The adopt pipeline requires each imported
   component be rewritten into local conventions, provenance-pinned
   (`Upstream-Ref:` trailer + `upstream: <path>@<sha>` in the registry), and
   pass a supply-chain review — the human review being "the security boundary."

So this doc records the triage; the maintainer decides what (if anything)
graduates into an adoption PR.

## What is already integrated (no action)

The obvious stack-agnostic tooling from these repos has **already** landed in the
core plugin — this triage confirms there is no remaining low-hanging fruit here:

| Capability | Source pattern | Already in plugin as |
|---|---|---|
| Block `git commit --no-verify` bypass | `block-no-verify.py` | `scripts/block-no-verify.py` (hook) |
| Block direct commits/pushes to `main`/`master` | `prevent-main-commit.*` | `scripts/prevent-main-commit.py` (hook) |
| Node version guard | `check-node-version.py` | `scripts/check-node-version.py` (hook) |
| Beads JSONL staging guard | `block-beads-jsonl-stage.py` | `scripts/block-beads-jsonl-stage.py` (hook) |
| Slack-webhook secret-hygiene guard | `block-slack-incoming-webhook.py` | `scripts/block-slack-webhook.py` (hook, PR #69) |
| TodoWrite → durable-tracker nudge | `nudge-todowrite-to-beads.sh` | `scripts/nudge-todowrite-to-tracker.py` (hook, PR #90) |
| Worktree lifecycle / `gc` | worktree hooks + skill | `git-worktree` skill + `gc` subcommand (PR #83) |
| Verification discipline | verification patterns | `verification-loop` skill (PR #61) |

The bulk of the agent-leverage hook cluster arrived in PR #61; this triage found
no additional guardrail hook that is both stack-agnostic and not already present.

## The one genuine gap worth adopting

**A React / Next.js performance best-practices skill.**

The marketplace has deep, opinionated framework coverage for **Rails/Ruby**
(`dhh-rails-style`, `kieran-rails-reviewer`, `andrew-kane-gem-writer`) and
**Python/TypeScript** review agents, plus a generic `frontend-design` skill and a
`julik-frontend-races-reviewer`. It has **no** skill that codifies React/Next.js
performance rules (render waterfalls, bundle size, re-render hygiene, RSC
boundaries). That is a real, framework-shaped hole in an otherwise
framework-rich catalog.

`agent-toolkit` contains a `react-best-practices` skill — a rules skill
(~40 rules across 8 categories, with a large `REFERENCE.md`) that fits the exact
shape of the marketplace's existing framework-specific skills. It is
self-contained (no external engine dependency), which makes it a clean adopt
candidate.

### Recommended integration path

Run it through the standard adopt pipeline rather than a raw copy:

1. **Register the source** in `docs/upstream-sources.md` (`scan: manual-only` to
   keep scheduled runs from fetching a private repo), recording license +
   provenance. Because the source is private, keep the entry minimal per the
   PRIVATE SOURCES rule.
2. **Adapt, don't blind-copy.** The `REFERENCE.md` is ~80 KB; trim and rewrite
   into the plugin's skill conventions (concise `SKILL.md` + progressive-
   disclosure reference) rather than importing verbatim.
3. **Verify ultimate provenance.** The rules trace back to public "Vercel
   Engineering" guidance; confirm the original source and license so attribution
   is pinned to the true origin, not just the intermediate repo.
4. **Bookkeeping:** bump `plugin.json` + `marketplace.json` skill counts + both
   READMEs, add a `CHANGELOG.md` entry, run `bun run docs:build`, and confirm
   `bun test` (the consistency + registry gates) stays green.

Optionally pair the skill with a lightweight `react-performance-reviewer` review
agent, mirroring how `kieran-typescript-reviewer` complements the TS skills — but
the skill alone is the high-value first step.

## Deferred — stack-specific, out of scope for the core plugin

The remaining components across the three repos are **application/stack-specific**
and belong in a consuming repo's own `.claude/`, not the stack-agnostic core:

- Data/ORM: Prisma migration + `db push` guards, schema-parity patterns.
- Platform SDKs: Clerk auth, Stripe webhooks, Inngest jobs, Dagster pipelines,
  PostHog analytics, S3 storage, AWS CDK.
- Product/domain skills: customer-success / user-recovery playbooks, and the
  personal-automation skills (finance, groceries, todoist, x-social).

These are correctly kept out; adopting them would dilute the core plugin's
stack-agnostic promise.

## Done-when

- [ ] Maintainer decides whether to open an adoption PR for the React/Next.js
      skill following the path above.
- [ ] If adopted: source registered (minimal, private-safe), skill adapted (not
      copied), provenance pinned to the true origin, counts/docs/changelog
      updated, `bun test` green.
