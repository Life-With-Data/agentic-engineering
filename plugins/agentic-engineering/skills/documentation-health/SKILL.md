---
name: documentation-health
description: Audit and repair the informational health of a repository's documentation — root & nested CLAUDE.md plus cross-tool agent context (AGENTS.md, CLAUDE.local.md, .claude/rules/, legacy tool configs), root & nested README, internal-facing docs, and external-facing docs. Use to run a periodic docs-health check, before a release, when onboarding a repo, when docs feel stale or bloated, or when asked to "check/fix/maintain the docs". Encodes cited best practices (Anthropic memory docs, Standard-Readme, Diátaxis, docs-as-code, GitHub community-health, the ETH Zurich & Vercel context-file evals) as concrete checkable rules plus a repair workflow.
allowed-tools:
  - Read
  - Edit
  - Write
  - Glob
  - Grep
  - Bash
---

# Documentation Health

> **Purpose:** Keep a repository's documentation *informationally healthy* — correct, current, well-scoped, non-duplicated, and pointing at the right source of truth — across all six documentation layers. Audit, repair, and (optionally) install a standing CI guardrail so health is maintained continuously, not just once.

This is a maintenance skill you run **repeatedly** on any repo. It does not assume this repo — point it at whatever you're maintaining.

## The one rule that anchors everything

**Single source of truth (SSOT): any fact that exists elsewhere in the repo — a count, a version, a date, a command list, an API signature — must be *referenced or generated*, never hand-copied into prose.** Every hand-copied fact is a drift landmine. The healthiest docs describe *where the authoritative value lives* (a generator, a test, a manifest) instead of restating the value. Reward this pattern where you find it; flag every violation.

## The six layers and their audiences

| Layer | Audience | Health question |
|-------|----------|-----------------|
| **Root CLAUDE.md** | The AI agent | Is it lean, specific, non-duplicative, and free of drifting facts? |
| **Nested CLAUDE.md** | The agent, scoped | Is subsystem detail scoped to where it's needed, with no contradictions? |
| **Root README** | The newcomer/consumer | Fastest path to value — title, description, install, usage, license — an index, not a manual? |
| **Nested READMEs** | Package consumers | Does each package explain its purpose, owner, status, local usage — without duplicating the root? |
| **Internal docs** | Maintainers/contributors | Are community-health files, ADRs, and ownership present and flowing? |
| **External docs** | Users | Diátaxis-clean, link-checked, fresh, and free of leaked internal content? |

The audiences are distinct and the checks enforce the separation — **README ≠ CLAUDE.md ≠ /docs.** README describes the project to a human; CLAUDE.md tells an agent *how to behave here*; /docs holds reference/how-to/explanation. They cross-reference; they never clone.

The CLAUDE.md layers include the **cross-tool agent context**: AGENTS.md (Claude Code does *not* read it natively — bridge with a one-line `@AGENTS.md` import or a symlink), git-ignored `CLAUDE.local.md` for personal overrides, `.claude/rules/` (rules without `paths:` load at launch, same cost as CLAUDE.md), and legacy per-tool configs (`.cursorrules`, …). Unbridged parallel copies drift — see [reference.md](reference.md) Layer 1b.

## Quick start

```bash
# Deterministic scan (zero dependencies; runs on any repo)
python3 ${CLAUDE_PLUGIN_ROOT}/skills/documentation-health/scripts/doc_health_check.py <repo-dir>

# JSON for tooling / CI. --fail-on tunes the gate's strictness:
#   error → fail only on ERROR   warn → ERROR or WARN
#   info  → any finding          never → report only, exit 0 (default)
python3 .../doc_health_check.py <repo-dir> --json --fail-on error
# (--strict is a back-compat alias for --fail-on error)
```

The script does the **deterministic** checks (line counts + a combined launch-context budget, missing sections, placeholder rot, broken `@imports`, hardcoded counts, unbridged CLAUDE.md↔AGENTS.md pairs, legacy tool configs, tracked/un-ignored `CLAUDE.local.md`, unscoped `.claude/rules`, raw `/init` boilerplate, emphasis density, linter-owned style rules, community-health completeness, ADR/CODEOWNERS presence, leak markers). It shells out to `lychee` (links), `doctoc` (TOC drift), and `markdownlint` (format) when installed, and skips them gracefully when not. The **judgment** checks (duplication, Diátaxis mode-mixing, stale commands, README↔CLAUDE.md drift, cross-tool contradictions, signal-to-noise) are yours — the script tells you which files to open.

## Workflow

Run these five phases. Phases 1–3 are read-only; **confirm with the user before Phase 4 writes anything.**

### 1. Discover
Map the documentation surface before judging it:
```bash
python3 .../doc_health_check.py <repo> --json   # inventory + deterministic findings
```
Also note: is there a `/docs` site generator (and does it default-deny or publish-everything)? A monorepo with packages? An `.github/` (local or org-level) supplying community-health defaults? A generator/test that owns counts (like this repo's `tests/plugin-consistency.test.ts`)?

### 2. Audit
Run the deterministic scan, then do the **judgment pass** by opening flagged files and applying the full checklist in [reference.md](reference.md). The high-value judgment checks nothing automates well:
- **CLAUDE.md signal-to-noise** — is each line something whose removal would cause Claude to make a mistake? Cut the rest.
- **Duplication / drift** — README vs CLAUDE.md onboarding steps; root vs package READMEs; any prose count vs its generator.
- **Stale commands** — do the README's install/usage commands still exist (`package.json` scripts, `Makefile`, CLI `--help`)?
- **Diátaxis mode-mixing** — a single doc page trying to be tutorial *and* reference *and* explanation at once.
- **Leak risk** — can any internal-tagged page reach the published bundle?
- **Cross-tool contradictions** — the same rule phrased differently in CLAUDE.md vs AGENTS.md vs legacy configs.
- **Behavioral spot-checks (optional, repo-read-only)** — in a fresh session, run the cold-start / constraint / command tests from [reference.md](reference.md)'s lifecycle section to verify CLAUDE.md actually steers the agent.

### 3. Report
Produce a scored report grouped by layer and severity (**ERROR / WARN / INFO** — see below). Lead with what's genuinely broken; separate "must fix" from "nice to have". Name the specific file and line for each finding and the concrete fix.

### 4. Repair (confirm first)
Apply fixes in dependency order. See the **Repair playbook** below. Prefer the *structural* fix over the cosmetic one — e.g. replace a hardcoded count with a pointer to its generator rather than just correcting the number.

### 5. Codify (compound)
Turn the audit into a standing guardrail so drift can't silently return — this is what makes health *continuous* rather than a one-time cleanup:
- **Add a CI gate.** Run the **setup** skill (`/setup`) — its "Docs CI" step installs [assets/doc-health.yml](assets/doc-health.yml) into `.github/workflows/` and walks through enabling the agent tier — or drop the workflow in by hand. It's a two-tier GitHub Actions template. Tier 1 (`scan`) is the deterministic gate: pick a `--fail-on` level to match how strict the team wants it (`error` for PRs, `warn` to also block drift, `never` to report-only). Tier 2 (`audit`) is the **agent in the loop** — it runs this skill via `anthropics/claude-code-action`, posts the judgment pass as a review *as Claude*, and **fails the check on a judgment-confirmed must-fix** (via a `--json-schema` structured output) so it can block merge — while still only *proposing* repairs, never pushing. Pin the workflow to a `v<version>` tag (produced by a manifest-version-triggered release workflow), not a moving branch. See [reference.md](reference.md) "Continuous integration".
- For agent-instruction drift, consider a `Stop` hook that proposes CLAUDE.md updates from the session.
- Adopt the CLAUDE.md add/prune policy ([reference.md](reference.md) lifecycle): add a rule on the *second* occurrence of a mistake, prune rules the agent demonstrably internalized, purge rules the moment a dependency they describe is swapped.
- Record any repo-specific documentation rule you had to reason out into the repo's own CLAUDE.md so the next pass starts smarter. Pairs with the **reflect-for-skill-updates** skill.

## Severity model

| Severity | Meaning | Examples |
|----------|---------|----------|
| **ERROR** | Broken or dangerous; fix now | No root README/LICENSE; secret in a doc; broken `@import`; dead links; placeholder text shipped in root README; CLAUDE.md far over the ceiling |
| **WARN** | Drift-prone or mis-scoped; fix soon | Hardcoded counts; missing community-health file; README > ~400 lines / no Usage; package without a README; internal marker on a publishable path; TOC out of sync |
| **INFO** | Advisory / hygiene | Missing ADRs or CODEOWNERS; prose/style; freshness nudges; missing TOC on a long README |

## Repair playbook

| Finding | Structural fix (preferred) |
|---------|---------------------------|
| CLAUDE.md over ~200 lines | Move path-specific rules into `.claude/rules/*.md` with `paths:` globs, or into a skill; delete generic filler and file-by-file maps. Imports do **not** save context — only on-demand mechanisms do. Match mechanism to content: skills go un-invoked without strong triggers (56% never fired in Vercel's evals), so must-know constraints stay in the lean always-loaded file. |
| CLAUDE.md and AGENTS.md diverged | Canonicalize AGENTS.md; reduce CLAUDE.md to `@AGENTS.md` + Claude-specific rules (symlink works on macOS/Linux; use the import on Windows). Fold in legacy `.cursorrules`/`.windsurfrules` too (`/init` merges them). |
| Style rules a linter already owns | Delete them — the formatter/linter config is the SSOT; keep only conventions tooling can't enforce. |
| Personal prefs / sandbox URLs in team CLAUDE.md | Move to a git-ignored `CLAUDE.local.md` (or `~/.claude/CLAUDE.md`); ensure `.gitignore` covers it. |
| Hardcoded count/version/date in CLAUDE.md or README | Replace with a sentence pointing at the generator/test/manifest that owns it; if a generator exists, generate the value between `<!-- GENERATED -->` markers instead of hand-editing. |
| README missing required section | Add Title / one-line description (<120 chars) / Install / Usage-Quickstart / License, in Standard-Readme order. |
| README bloated into a manual | Move reference/how-to/deep-dive content into `/docs`; leave an index + quickstart that links out. |
| Package dir without README | Add purpose + owner/contact + status + local-usage; link *up* to root for workspace setup (don't restate it). |
| README duplicates CLAUDE.md | Keep human onboarding in README; in CLAUDE.md `@import` the README and keep only agent-behavior rules. |
| Missing community-health file | Add `CONTRIBUTING`/`CODE_OF_CONDUCT`/`SECURITY`/`SUPPORT` (root, `.github/`, or `docs/`) — but first confirm an org-level `.github` repo isn't already supplying a default. |
| Doc mixes Diátaxis modes | Split by mode; leave the tutorial minimal and *link* to the explanation/reference instead of inlining it. |
| Internal content on a publishable path | Fence it (`docs/internal/` or `internal/`), switch the generator to an allowlist (default-deny), and add a CI diff that fails if internal-tagged pages reach the rendered bundle. |
| Missing ADRs in a churning repo | Start `docs/adr/` (Nygard/MADR); ADRs are append-only — supersede, never edit an accepted one. |

## Anti-patterns to flag (quick reference)

- **CLAUDE.md:** dumping everything into root; duplicating the README; file-by-file maps; frequently-changing facts (counts/versions/dates); generic best-practice filler; secrets; assuming `@import` reduces context (it doesn't); raw `/init` output shipped uncurated; prose restating linter-owned style; personal config in the team file (belongs in git-ignored `CLAUDE.local.md`); ALWAYS/NEVER walls (prefer "prefer X; exception: Y"; hooks for zero-exception rules); an unbridged AGENTS.md twin.
- **README:** written for the maintainer instead of the newcomer; growing into a manual; placeholder/template text; dead badges/links; a hand-maintained fact a generator could own.
- **Docs:** a single page mixing Diátaxis modes; internal notes one static-site build away from publication; a decision log that went silent; hand-maintained reference that should be generated; load-bearing GitHub Wiki (bypasses PR review, CODEOWNERS, and CI).

## Scope discipline

- Audit is read-only; **never write during Phases 1–3.** Get explicit confirmation before repairs.
- Adding community-health files, opening PRs, or publishing docs are outward-facing — confirm before doing them.
- **In non-interactive CI (the `audit` tier) there is no human to confirm, so the standing gate replaces it: propose, never apply in place.** Post a review or open a *draft* PR; never push repairs to a protected branch. The PR review *is* the confirmation step.
- Don't mandate structure a repo doesn't need. Diátaxis is a *compass, not a filing cabinet*: flag mode-mixing within a page, but don't force four literal folders onto a small project. A thin CLAUDE.md section is better deleted than padded.

## Reference & related

- Full cited per-layer checklist and thresholds: [reference.md](reference.md)
- Scanner: [scripts/doc_health_check.py](scripts/doc_health_check.py)
- Example CI workflow (deterministic gate + agent-in-the-loop audit): [assets/doc-health.yml](assets/doc-health.yml)
- **compound-docs** — captures a solved problem; run this after to check the docs you touched are healthy.
- **reflect-for-skill-updates** — when a docs gap let a mistake happen, codify the fix here or in CLAUDE.md.
- **create-agent-skills** — conventions for the CLAUDE.md/rules/skills split this skill enforces.

**Activation keywords:** documentation health, docs audit, check my docs, maintain docs, CLAUDE.md too long / bloated, README missing sections, stale docs, doc drift, docs review, community health files, ADR, Diátaxis, internal vs external docs, doc rot, informational health, AGENTS.md drift, cursorrules, agent context files, CLAUDE.local.md, cross-tool agent configs.
