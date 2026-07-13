# Changelog

All notable changes to the agentic-engineering plugin will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [3.21.0] - 2026-07-13

### Added

- **Sub-issue status is now a first-class, stakeholder-readable track.** Sub-issues decompose a parent and roll up into the *parent's* PR, so they never earn their own `in_review`/`shipped` board stage — which left them with only open/closed as visible state, too coarse for a business stakeholder to read "what is happening right now." The lifecycle engine gains a **`--sub-status <N> <in_progress|in_review|blocked|done>`** verb that drives a **mutually-exclusive `status:*` label** (`status:in-progress` / `status:in-review` / `status:blocked`; `done` strips every `status:*` label and closes the issue as completed — an orchestrator close, not a PR auto-close). Labels are repo-scoped, so the verb needs **no board** and runs in `github` mode too, self-creating its labels with colors that mirror the stage palette. The invariant — at most one `status:*` label per issue — is enforced by the verb (a swap, not an add) and covered by seven new cases in [`tests/lifecycle_board_test.py`](tests/lifecycle_board_test.py). Defined in the [`lifecycle`](skills/lifecycle/SKILL.md) skill (new *Sub-issue status* section + one-writer table row) with the concrete `gh` calls in [`references/gh-recipes.md`](skills/lifecycle/references/gh-recipes.md).
- **Seam gate + drift flag against status snowballing.** Because agents don't deterministically do the right thing, the lifecycle now *verifies a predecessor step finished before allowing the next transition*, at the one seam where a mistake gets buried: `--set-status <N> in_review` **refuses** (`error_code: open_sub_issues`) when the parent still has open sub-issues — enforcing in the engine what `/workflows:work` Phase 4 only stated in prose, so an agent that skips the checklist can't mark a parent ready-for-review and let the merge → `shipped` automation quietly ship unfinished decomposed work. The reconciler and deliberate operator/CI moves pass through with `--force`; a new report-only reconciler flag **`in_review_with_open_subissues`** catches parents that reached that state via a forced/out-of-band path (rule-5 reality-sync, a human drag). Both use data already fetched (no extra queries) and are covered by six new tests. Deliberately scoped to this one high-value seam — sub-issue label-residue scans and board-wide audits were assessed as overkill.
- **`/lifecycle-doctor` now verifies the one native automation the lifecycle depends on** — the built-in "Item closed" Projects workflow is the sole writer of `→ shipped` (no engine verb owns it), so a human silently disabling it means merged PRs close issues but Status never advances to `shipped`. The doctor gains an `item_closed_workflow` check (via a new `project_workflows` API reader) that FAILs if it is off — bootstrap only checked it once at setup; the doctor now re-checks every run. GitHub's Projects API exposes only a workflow's `name`/`enabled` (never its action config) and no enable/create mutation, so `enabled` is the one bit that can be verified.

### Changed

- **`/workflows:work` and `/workflows:orchestrate` now drive sub-issue status at the execution boundaries** — dispatch → `in_progress`, hand-back → `in_review`, acceptance verified → `done` (replacing the raw `gh issue close`), open `blocked-by` → `blocked`. The **owning agent writes every `--sub-status`; dispatched sub-agents never touch GitHub state**, preserving the one-writer invariant so status stays faithful whether the owner implements inline or delegates. Component counts (agents/commands/skills) unchanged — this extends the engine and existing commands.
## [3.20.1] - 2026-07-13

### Added

- **`documentation-health` gains first-class GitHub Actions support.** A new example workflow ([assets/doc-health.yml](skills/documentation-health/assets/doc-health.yml)) ships two independent tiers: a deterministic `scan` gate that fetches the zero-dependency scanner at a pinned ref, and an opt-in `audit` job that runs the skill inside `anthropics/claude-code-action` for the **agent-in-the-loop** judgment pass (duplication, Diátaxis mode-mixing, stale commands, README↔CLAUDE.md drift). The audit posts its review *as Claude* (the Claude GitHub App identity) and is **propose-only yet blocking**: it never pushes to a protected branch, but emits a `--json-schema` structured output and **fails the check on a judgment-confirmed must-fix**, so a real problem blocks merge while scanner false positives don't. The skill is dogfooded on this very marketplace via live repo workflows (`.github/workflows/doc-health.yml`).
- **Manifest-version-triggered release automation** (`.github/workflows/release.yml`): on push to `main`, reads the plugin version and cuts an immutable `v<version>` tag + GitHub Release (notes from the CHANGELOG) when it's new. Chosen over release-please/conventional-commits because the repo already hand-bumps the manifest and maintains the changelog under test — those tags are what the doc-health workflow and external consumers pin to.
- **One-click adoption via `/setup`.** The setup skill gains a "Docs CI" step that installs `.github/workflows/doc-health.yml` into the target repo and walks through enabling the agent tier — generate a `CLAUDE_CODE_OAUTH_TOKEN` (Pro/Max subscription, via `claude setup-token`) or `ANTHROPIC_API_KEY` secret, install the Claude GitHub App, and mark the checks Required. The scan gate needs no secret; the audit tier accepts a subscription token (pass exactly one credential — an empty second one breaks auth). Reciprocal pointers in the skill and README make the path obvious from either entry point, and both READMEs now route install → `/setup` with a "Configure" step so the capability surfaces through the marketplace's config flow rather than sitting behind a skill users must already know to invoke.

### Changed

- **The scanner (`doc_health_check.py`) gains tunable gate strictness via `--fail-on {error,warn,info,never}`** (default `never`; `--strict` is kept as a back-compat alias for `--fail-on error`). Teams can start at `error` on PRs and ratchet to `warn` once drift is burned down, or run `never` for report-only scheduled sweeps. `SKILL.md` and `reference.md` document a "Continuous integration" section covering the two tiers, the strictness dial, the propose-only-yet-blocking rule, and tag-based pinning. No component counts change.

## [3.20.0] - 2026-07-13

### Added

- **New `block-db-push.py` PreToolUse hook** — blocks `prisma db push` (and its `npx`/`pnpm`/`dotenv` wrapper forms plus `pnpm --filter <pkg> push` script aliases) before it runs. `db push` mutates the live database to match `schema.prisma` *without* writing a migration, silently drifting the schema from the migration history; that breaks tests which apply migrations from scratch and means CI/CD and production (which deploy by running migrations) never receive the change. This is the DB-safety sibling of the existing `prevent-main-commit` / `block-no-verify` git guards, and like `check-node-version.py` it is inert unless a project actually runs `prisma db push`, so non-Prisma repos pay nothing. Precision-guarded (quote-stripped so prose/`grep`/`echo` mentions and legitimate `migrate dev` / `migrate deploy` / `generate` commands are never blocked) and covered by [`tests/block_db_push_test.py`](tests/block_db_push_test.py). Documented in [`scripts/HOOKS.md`](scripts/HOOKS.md). Adapted from the first-party `agent-leverage` / `bluestar-intel` repos. Component counts (agents/commands/skills) unchanged — hooks are not counted.

## [3.19.0] - 2026-07-12

### Added

- **New `acceptance-criteria-reviewer` agent** — a focused reviewer whose sole job is to hold a change against the **documented Acceptance Criteria and Validation steps** of its tracker issue, criterion by criterion, and emit a `PASS` / `FAIL` / `INCOMPLETE` verdict with `file:line` evidence. It deliberately ignores code style, security, performance, and architecture (other agents own those) — the narrow scope and separate context window are the point: an independent verifier, not the author, decides whether "done" is actually done. A criterion is met only when the diff demonstrably makes it true; "can't tell" and "CI is green but no test covers the criterion" both count as *not met*. Review agent count 16 → 17; total agents 30 → 31.

### Changed

- **`/workflows:review` now runs the acceptance-criteria-reviewer on every pass as the gating conformance check.** Its `FAIL` verdict and each unmet/partial criterion or absent validation step fold into synthesis as **P1 findings** — and because `land-pr`'s merge gate already blocks on unresolved P1s, acceptance-criteria conformance becomes an *enforced* gate rather than implementer self-attestation. This closes the loop opened in 3.18.1, where the criteria and Validation sections were documented but no independent review step evaluated or gated on them.
- **`/workflows:work` Phase 3 gains an optional acceptance-criteria pre-check** — the *same* agent, invoked in the implementer's own session before opening the PR, but **advisory only** (a smell-test, never the gate), so AC gaps are cheap to fix before the PR exists. This mirrors the repo's existing two-tier pattern: inline pre-check for focus/speed, independent stage for enforcement. Context separation is preserved because the authority to gate lives only with the independent review stage, never with the party being evaluated.

## [3.18.1] - 2026-07-12

### Added

- **Canonical issue and sub-issue body templates for the eng workflow** — [`scripts/templates/issue-template.md`](scripts/templates/issue-template.md) (parent) and [`scripts/templates/sub-issue-template.md`](scripts/templates/sub-issue-template.md) (task unit) codify best-practice structure with standard sections: **Overview**, Problem Statement / Context, Proposed Solution / Implementation Notes, Scope, System-Wide Impact, External System Wiring, Task Breakdown, **Acceptance Criteria**, **Validation** (how a reviewer proves it *behaves*, not merely compiles — exact commands + expected result, plus manual and rollback steps), and Dependencies & Risks. `/workflows:plan` Step 7 now copies the sub-issue template for every `<task_body_file>` it creates under a parent, so decomposed tasks share one standard shape instead of an undefined ad-hoc body.

### Changed

- **`/workflows:plan`'s three plan-doc tiers (MINIMAL / MORE / A LOT) now each carry a `Validation` section** alongside Acceptance Criteria, and Step 4 points at the canonical templates as the reusable source of truth for both parent and sub-issue bodies. Closes the gap where "done" was asserted via acceptance criteria but never tied to a concrete verification the reviewer could run. No component counts change (templates are supporting assets, not agents/commands/skills).

## [3.18.0] - 2026-07-11

### Added

- **New `/workflows:groom` command** — the grooming segment of the pipeline as a first-class flow, supporting the standard bifurcated workflow (intake → groomed work; groomed work → implemented work). It drives an idea, bug report, or stub issue through brainstorm → plan and **stops once the work is groomed**: Status `planned` on the board, a join-keyed plan doc, and sub-issues with dependencies — exactly the bar `/workflows:work`'s entry gate enforces before a claim. Autonomous by default with a decision log (`--steer` for an interactive grooming session), idempotent on already-groomed items (re-runs report and stop; later stages are never re-groomed or regressed), provenance-gated for outsider-authored issues, and hard-stopped: it never claims, never branches, never writes product code, never opens a PR. It owns no lifecycle transition of its own — it sequences the existing `/workflows:brainstorm` and `/workflows:plan` writers and reads state through the `orchestrate` gate (a pure state read), so the one-writer-per-transition table is unchanged. Bug reports get grooming-specific handling: optional reproduction validation via `bug-reproduction-validator` when cheap and side-effect-free, with "can't reproduce" treated as a legitimate grooming outcome rather than a failure. Command count 27 → 28.

### Changed

- **`/workflows:orchestrate` gains pipeline-segment flags**, orthogonal to the autonomy flags: `--groom` runs only intake → groomed and stops (the `/workflows:groom` spec is normative — same ladder, same hard stop, same groomed packet), while `--implement` starts from groomed work and **refuses to groom on the fly** — an item below `planned`, or one whose plan doc is missing, routes to `/workflows:groom` instead of being silently planned mid-run, so grooming can be reviewed separately before code gets written. `--implement` with empty input pulls from `--ready-work` as before (its items are groomed by definition). The default end-to-end behavior is unchanged.
- `/workflows:plan`'s pipeline-mode note and the `lifecycle` skill's description/gate section now name `groom` alongside `orchestrate` as a pipeline driver; `FLOWS.md` documents the groom flow and the bifurcation boundary at `planned`.

## [3.17.7] - 2026-07-11

### Changed

- **`documentation-health` now audits the cross-tool agent-context layer and the CLAUDE.md lifecycle.** Sourced from a deep-research review of CLAUDE.md-management practices, with every load-bearing claim verified against primary sources before adoption (official memory docs, ETH Zurich's arXiv:2602.11988, Vercel's skills-vs-AGENTS.md evals). The scanner gains deterministic checks for: unbridged `CLAUDE.md`+`AGENTS.md` pairs (Claude Code doesn't read AGENTS.md natively — the official bridge is a thin `@AGENTS.md` import or symlink), `AGENTS.md` with no bridge at all, legacy per-tool configs (`.cursorrules`, `.windsurfrules`, `GEMINI.md`, `.cursor/rules/`, …), tracked or un-gitignored `CLAUDE.local.md`, `.claude/rules/*.md` hygiene plus unscoped rules (no `paths:`) feeding a new combined launch-context budget, raw `/init` boilerplate shipped uncurated, shouted-emphasis density, and style rules in prose when a formatter/linter config owns them; `./.claude/CLAUDE.md` is now correctly treated as root-level. `reference.md` adds Layer 1b (cross-tool context), CLAUDE.local.md/rules checks, a "CLAUDE.md lifecycle" section (two-strike add rule, adherence-based pruning, upgrade-triggered purges, and four behavioral verification tests: cold-start / constraint / command / noise-reduction), and an empirical-grounding note (context files add >20% inference cost without generally improving success; skills went un-invoked in 56% of Vercel's eval cases without triggers). Rejected from the same source doc after verification: a wrong import-depth claim (it said five hops; official docs say four, as the skill already stated), a misquoted eval number (94% vs the actual 56%), and rumor-tier content ("KAIROS" daemon, "Auto Dream" internals). No component counts change.

## [3.17.6] - 2026-07-11

### Added

- **New `documentation-health` skill** — audits and repairs the informational health of a repository's documentation across all six layers (root & nested `CLAUDE.md`, root & nested `README.md`, internal-facing docs, external-facing docs). It encodes cited best practices — Anthropic's CLAUDE.md memory guidance (~200-line ceiling, no drifting counts, `@import` vs on-demand loading), the Standard-Readme required-section spec, Diátaxis mode-separation, docs-as-code hygiene, and GitHub community-health/ADR/CODEOWNERS conventions — as a concrete rule set anchored by one principle: *any fact that lives elsewhere (a count, version, date, command) must be referenced or generated, never hand-copied.* Ships a **Discover → Audit → Report → Repair → Codify** workflow (`SKILL.md`), a full cited per-layer checklist (`reference.md`), and a zero-dependency Python scanner (`scripts/doc_health_check.py`) that runs on any repo and shells out to `lychee`/`doctoc`/`markdownlint` when present. Skill count 34 → 35.

## [3.17.5] - 2026-07-11

### Changed

- **The compounding-knowledge PR is now always submitted with GitHub auto-merge enabled.** The `land-docs` skill (compound's Phase 3 data lane) previously opened the docs-only PR, blocked on `gh pr checks --watch`, then merged by hand — which meant the merge depended on the session staying alive until CI finished. It now arms GitHub-native auto-merge (`gh pr merge --auto --squash --delete-branch`) in the same step the PR is opened, gated only by the docs-only scope check, so the knowledge PR lands the instant checks go green even if the session has already ended. If the repo lacks "Allow auto-merge" the skill reports it as a settings blocker and falls back to watch-then-merge. `/workflows:compound` Phase 3 and `/workflows:orchestrate`'s compound row are updated to match. No component counts change.

## [3.17.4] - 2026-07-11

### Fixed

- **Caught one landing-page stat the previous release missed** — a "Delegate" pillar tool-tag still read "29 specialized agents". Converted it to a nested `data-stat="agents"` span so the generator fills it (now 30) like every other stat. Completes the drift-proofing from v3.17.3.

## [3.17.3] - 2026-07-11

### Fixed

- **Landing-page stats are now generator-owned and drift-proof.** The docs site's hero, call-to-action, and "Version X released" eyebrow carried hand-written counts that had gone stale ("29 agents, 23 commands, 18 skills", "Version 2.32.2") while the real marketplace-wide totals were 30 / 27 / 35 and the version was 3.17.x. Every on-page stat is now marked `data-stat="<key>"` (agents/commands/skills/mcp/version) and filled by `scripts/generate-docs.ts` from the live component counts and plugin version on every `bun run docs:build`; `bun run docs:check` (CI) fails if any committed value is stale, and `tests/plugin-consistency.test.ts` asserts every occurrence matches the filesystem. SEO `<meta>` descriptions that cited counts were made evergreen (count-free) so they can't drift either. No plugin components change.

## [3.17.2] - 2026-07-11

### Changed

- **Standardized the project name to "Agentic Engineering" across outward-facing surfaces.** Renamed the "Compounding Engineering" / "compounding engineering" brand and philosophy label to "Agentic Engineering" in the root and plugin READMEs/CLAUDE.md, the docs site (`docs/index.html` title, Open Graph/Twitter meta, logo, hero, philosophy sections) and every `docs/pages/*.html` chrome title/meta/logo (`CE Docs` → `AE Docs`), `FLOWS.md`, `orchestrate.md`, `HOOKS.md`, and the `reflect-for-skill-updates` / `headroom` skills. Left intentionally intact: the `/workflows:compound` command, `compound-docs` skill, and standalone "compounding" descriptions of the accumulation mechanic (these name an action, not the product); historical CHANGELOG entries; and every provenance reference to the upstream `EveryInc/compound-engineering-plugin` repo (its actual name) and former `plugins/compound-engineering` paths in archived plans. No component counts change.

## [3.17.1] - 2026-07-11

### Changed

- **De-branded outward-facing references to the original upstream (Every / every.to).** The project began as a fork and has since diverged substantially into its own thing; this removes the upstream company and repo from user-facing surfaces. The `every-style-editor` agent and skill are renamed to **`editorial-style-editor`** (directory, frontmatter `name`, and the bundled style reference `EVERY_WRITE_STYLE.md` → `EDITORIAL_STYLE.md`), with "Every's style guide" rewritten as "our editorial style guide" throughout and the Every-specific brand-capitalization rule dropped. The `agent-native-architecture` reference examples that named the "Every Reader" product are genericized to "a reader app." Root `README.md` (attribution blockquote + external "Learn more" links), the docs-site footer (`docs/index.html`), and the plugin `homepage` fields now point at our own docs site instead of every.to. Historical CHANGELOG attribution and upstream-adoption provenance records (`docs/upstream-sources.md`, the fork-trap notes in `CLAUDE.md`) are intentionally left intact — they are accurate history and load-bearing operational records, not branding. No component counts change.

## [3.17.0] - 2026-07-10

### Added

- **`doubt-driven-development` skill — in-flight adversarial review of non-trivial decisions, adopted and adapted from [addyosmani/agent-skills](https://github.com/addyosmani/agent-skills).** Where `verification-loop` and `/workflows:review` are post-hoc gates on a finished artifact, doubt-driven is an in-flight posture: it materializes a fresh-context reviewer — biased to disprove, not approve — before any non-trivial decision stands. The loop is **CLAIM → EXTRACT → DOUBT → RECONCILE → STOP**: name the decision and why it matters, extract the smallest reviewable artifact + contract, hand the reviewer **ARTIFACT + CONTRACT but never the CLAIM** (passing the conclusion biases toward agreement), then classify every finding in strict precedence (contract-misread / valid-actionable / valid-trade-off / noise) and stop on trivial findings, a hard 3-cycle bound, or user override. Includes a "doubt theater" checkable signal (two+ cycles of substantive findings with zero classified actionable = validating, not doubting), rationalization/red-flag tables, and a heavily-gated **cross-model escalation** protocol (read-only sandbox, prompt piped via stdin not argv, explicit per-invocation user authorization, announced skips in non-interactive contexts). Retargeted to local components: the fresh-context reviewer roster points at the `agentic-engineering` review agents (`security-sentinel`, `architecture-strategist`, `code-simplicity-reviewer`, `integration-boundary-reviewer`, `pattern-recognition-specialist`, the `kieran-*` reviewers) spawned per `orchestrating-swarms`; docs-fact verification points at the context7 MCP; the post-hoc counterpart is `/workflows:review` + `verification-loop`; TDD's RED step (`test-driven-development`) is doubt made concrete for behavioral claims, with `test-strategy-reviewer` covering coverage quality at review time; reviewer-surfaced failure modes hand off to `debugging-and-error-recovery`. Provenance pinned in `docs/upstream-sources.md`. Skills 33 → 34.

## [3.16.0] - 2026-07-10

### Added

- **`api-and-interface-design` skill — design-time contract authoring for REST/GraphQL endpoints, module boundaries, component props, and type contracts** (adopted from [addyosmani/agent-skills](https://github.com/addyosmani/agent-skills), `skills/api-and-interface-design/SKILL.md@4e8bd9fd`, adapted). Fills a genuine gap: the plugin's `architecture-strategist` and `integration-boundary-reviewer` agents both inspect an interface *after* the code is written, and nothing local covered shaping a contract *before* it exists. The skill carries the upstream's Hyrum's Law framing (every observable behavior — error text, timing, ordering — becomes a de facto contract once someone depends on it), the One-Version Rule, branded types for IDs (`type TaskId = string & { readonly __brand: 'TaskId' }`), discriminated-union status modeling, input/output type separation, the HTTP status-code and naming-convention tables, and a rationalizations table. Adaptations: a **Positioning** section stating the design-time-vs-review-time split against the two review agents; the upstream's `deprecation-and-migration` sibling reference (not adopted here) retargeted to the local `data-migration-expert` agent for the data-layer-migration facet; frontmatter description and voice conformed to house style (imperative, what + when). Supply-chain review: single prose SKILL.md, no scripts/network/dependencies — clean. Skills 32 → 33.

## [3.15.0] - 2026-07-10

### Added

- **`debugging-and-error-recovery` skill — the root-cause debugging methodology that sits above the plugin's existing reproduce-and-file tools.** Adopted and adapted from [addyosmani/agent-skills](https://github.com/addyosmani/agent-skills) (`skills/debugging-and-error-recovery/SKILL.md@4e8bd9fd`, MIT, supply-chain reviewed). Codifies stop-the-line on any unexpected failure, then a six-step triage checklist — reproduce, localize, reduce, fix the root cause, guard, verify. Its high-value content is preserved intact: the **non-reproducible-bug decision tree** (branch on timing / environment / state / randomness, with tactics like artificial delays to widen race windows and load to raise collision probability), the **symptom-vs-root-cause** worked example (fix the JOIN, not `[...new Set(users)]` in the UI), a **`git bisect run`** regression recipe, the calibrated "you might be right 70% of the time; the other 30% costs hours — reproduce first" rationalization, and a **"Treating Error Output as Untrusted Data"** section (never execute commands or URLs embedded in stack traces or CI logs) that mirrors this repo's own untrusted-input posture. Positioned explicitly as the broader triage *methodology*: it points to the `/reproduce-bug` and `/report-bug` commands and the `bug-reproduction-validator` agent for the concrete reproduce-and-file workflow so their triggers stay distinct, and hands off to the `verification-loop` skill for the pre-PR quality pass. Generic per-error triage trees (TypeError, CORS, white screen) tightened; stack-specific commands marked illustrative to keep the methodology language-agnostic. Skill count 31 → 32.

## [3.14.0] - 2026-07-10

### Added

- **`sdd-cache` — an opt-in, revalidating `WebFetch` doc cache (adopted from [`addyosmani/agent-skills`](https://github.com/addyosmani/agent-skills), ported bash→python3).** A `PreToolUse`/`PostToolUse` (WebFetch) hook pair that caches fetched documentation on disk so an agent consulting the same official docs across sessions stops re-downloading identical pages — **without weakening the "verify against current docs" guarantee.** The load-bearing property is that there is **no TTL**: the pre hook looks up the cached entry by `sha256(url)` (32 hex chars) under `.claude/sdd-cache/`, and if it carries an `ETag`/`Last-Modified` validator, sends a conditional `HEAD` (`If-None-Match`/`If-Modified-Since`, 5s timeout, follows redirects) to that same URL; it serves the cached body and blocks the fetch (`exit 2`, the same deny signal `block-no-verify.py` uses) **only** on a real `304 Not Modified` — a live re-verification, not a memory read. Any other outcome (`200` = changed, error, timeout, or an entry with no validator) lets the real `WebFetch` proceed. The post hook `HEAD`s the URL to capture validators from the final redirect hop and writes `{url, prompt, etag, last_modified, content, fetched_at}` atomically; a response with no validator is never cached (it could never be revalidated) and any stale entry is removed. **Opt-in posture** (a condition of the adoption): both hooks are **inert unless `AGENTIC_SDD_CACHE=1`** is set — following the v3.7.0 opt-in precedent (off by default, explicit signal) but via an environment variable rather than a committed frontmatter flag, since caching is a per-machine choice that shouldn't ride a PR and flip on for every clone (and so it stays off the `agentic-engineering.local.md` config surface). Both fail-open on any error, so a broken cache can never block a legitimate fetch. The two upstream bash scripts were ported to python3 (stdlib `urllib`/`hashlib`/`json` — `curl`→`urllib.request`, `jq`→`json`, `shasum`→`hashlib`) to match every other hook in `scripts/`; `.claude/sdd-cache/` is gitignored. Supply-chain reviewed line-by-line (the only network egress is a conditional `HEAD` to the same URL the agent already intends to fetch — no exfiltration; writes confined to the cache dir; no `eval` of fetched content). Pinned by `sdd_cache_pre_test.py` / `sdd_cache_post_test.py` (offline: the revalidation call is mocked, including the safety-critical "`200` ⇒ never serve stale" path and the cross-hook shared-key invariant). Documented in `README.md` (Hooks) and `scripts/HOOKS.md`. Provenance: `addyosmani/agent-skills@4e8bd9fde4a38cd009053e649f4cdc7cd36b568b`. No component count changes — hook addition only.

## [3.13.0] - 2026-07-10

### Added

- **`test-driven-development` skill — the test-*authoring* discipline, adopted (adapted) from `addyosmani/agent-skills`.** Fills the gap on the write side of testing: RED-GREEN-REFACTOR, the **Prove-It pattern** (every bug fix starts with a failing reproduction test), the test pyramid plus a Google-style **test-size resource model** (Small = no I/O, ms / Medium = localhost, s / Large = external, min), the test-double **preference order** (real > fake > stub > mock, mock only at boundaries), state-not-interactions assertions, DAMP-over-DRY, the Beyonce Rule, and the efficiency rule "after a clean run, don't re-run the same command unless code changed." Explicitly positioned as the authoring complement to the review-time `test-strategy-reviewer` (audits existing tests) and the `verification-loop` gate (runs the suite before done), so the three skills' triggers don't collide. Co-locates an adapted `references/testing-patterns.md` (framework-generic Arrange-Act-Assert, naming, assertions, mocking-at-boundaries, component/API/E2E examples). The upstream browser-testing section is retargeted from Chrome DevTools MCP to the local `agent-browser` skill and `/test-browser` command, and the "sibling reference" pointers now name only components that exist here. Skills 30 → 31. Provenance pinned in `docs/upstream-sources.md`.

## [3.12.0] - 2026-07-10

### Added

- **`security-and-hardening` skill — the build-time security playbook that complements the audit-time `security-sentinel` agent.** Adopted (adapted) from [addyosmani/agent-skills](https://github.com/addyosmani/agent-skills) via the `/upstream-scan` triage pipeline. Where `security-sentinel` reviews finished code ("did they build it safely"), this skill guides hardening *during* implementation ("how to build it safely") — the two are stated as complementary in the skill so their triggers don't collide. Substance preserved in full: a five-minute **threat-model-first** process running STRIDE over each trust boundary (with mitigations) and writing abuse cases next to use cases; a three-tier **Always / Ask-First / Never** boundary system; OWASP Top 10 prevention patterns including an **SSRF allowlist** built on `ipaddr.js` `range() !== 'unicast'` that names its own residual **TOCTOU / DNS-rebinding** gap and the pinned-IP mitigation; a reachability-keyed **`npm audit` triage** decision tree ("is the vulnerable function actually called in your code path?") plus supply-chain hygiene (lockfile + `npm ci`, `postinstall` wariness, typosquat watch); and a full **OWASP LLM Top 10** section treating model output as untrusted data (no `eval`/SQL/`innerHTML`/shell), with prompt-injection, excessive-agency, and unbounded-consumption guidance. Co-locates the upstream security checklist as a skill reference ([security-checklist.md](skills/security-and-hardening/references/security-checklist.md)), linked from `SKILL.md`. Provenance pinned to `addyosmani/agent-skills@4e8bd9fde4a38cd009053e649f4cdc7cd36b568b`; both source files passed supply-chain review (pure documentation — no scripts, network calls, or embedded instructions). Skills 29 → 30.

## [3.11.0] - 2026-07-10

### Added

- **`observability-and-instrumentation` skill — instrument-as-you-build discipline so a feature ships with the telemetry to operate it, not archaeology after the first incident.** Adopted and adapted from `addyosmani/agent-skills` (skill + its repo-root observability checklist, co-located here as [references/observability-checklist.md](skills/observability-and-instrumentation/references/observability-checklist.md)). Codifies the parts most teams get wrong: a signal-selection table (structured log vs metric vs trace, each with a cost profile — "metrics tell you *that*, traces *where*, logs *why*"), RED for endpoints / USE for resources, a hard cardinality denylist (user_id, email, request_id, full URL, and error text are **never** metric labels), "percentiles always, averages never", symptom-vs-cause alerting (error rate > 1% for 5 min pages; CPU at 85% does not), a log-level → on-call-action table, and a verify-the-telemetry step (force an error in staging, find it by `requestId`). Complements the audit-time `security-sentinel` agent (secret-in-logs) and the `performance-oracle` agent (measured slowness); illustrative OpenTelemetry/Prometheus snippets are examples only. Skills 28 → 29.

## [3.10.0] - 2026-07-10

### Added

- **`interview-me` skill — confidence-gated intent extraction that runs upstream of `brainstorming`.** Adopted and adapted from `addyosmani/agent-skills` (`skills/interview-me/SKILL.md`). What the user asks for and what they actually want are different things ("build me a dashboard" is a convention, not a solved problem); this skill closes that gap before any spec, plan, or code exists, when switching costs are still zero. The mechanic is a mandated `HYPOTHESIS / CONFIDENCE ~N% — missing:` opener, then **one question at a time** each carrying a falsifiable `GUESS:` (the user reacts to a wrong guess faster than they generate an answer, which also surfaces the interviewer's own assumptions), a "want vs. should-want" detector for buzzword goals ("scalable", "clean", "modern") whose probe is *"If you didn't have to justify this to anyone, what would you actually want?"*, an anti-sycophancy rule, rejection of false confirmations ("Whatever you think is best" → re-ask with two concrete options), a checkable stop condition (*"Can I predict the user's reaction to the next three questions?"*), and a restate template with a non-negotiable **Out-of-scope** line. It explicitly refuses non-interactive contexts (CI, `/loop`, autonomous loops), flagging underspecification as a blocker instead of guessing. Positioned deliberately relative to `brainstorming` — interview-me extracts **what** the user wants (intent); brainstorming explores **how** to build it (approaches) — so their adjacent triggers order rather than collide, then it hands off to `brainstorming` and `/workflows:plan`. Optional user-confirmed persistence to `docs/intent/YYYY-MM-DD-<topic>-intent.md`, mirroring where `brainstorming` saves its design docs. Supply-chain review: clean (pure-prose skill, no remote fetches, scripts, or exfiltration). Skills 27 → 28. Provenance pinned in `docs/upstream-sources.md`.

## [3.9.0] - 2026-07-10

### Added

- **`/config-flags` — discoverable config surface for every opt-in flag the plugin offers.** `scripts/config_registry.py` is the single declared inventory of per-repo configuration flags read from `agentic-engineering.local.md` (and, for board identity, the committed `agentic-engineering.md`): a `ConfigFlag` dataclass (key/kind/default/description/owner/file/choices/toggleable) per flag, with `--inventory`/`--get`/`--set` verbs sharing `lifecycle_board.py`'s existing atomic-write, tracked-file-guard, and `{ok, error_code, error, fix}` error contract — writes are refused outright if `agentic-engineering.local.md` is tracked in git, never silently overwritten. Retrofits the four flags that previously shipped with zero central discoverability (`issue_tracker`, `review_agents`, `plan_review_agents`, `nudge_todowrite` from v3.7.0) plus the two board-identity keys (`github_project_owner`/`github_project_number`, inventoried but never toggleable). `/config-flags` (named to avoid colliding with the built-in `/config`) browses the full inventory and flips a flag via `AskUserQuestion`; `/lifecycle-doctor` gains a read-only **Configuration** section (SET/UNSET vocabulary, distinct from its PASS/WARN/FAIL/SKIP health checks) over the same inventory; the `setup` skill now delegates its flag writes to the shared writer instead of hand-templating frontmatter (and, as a side effect, no longer risks silently overwriting a tracked local config — the writer refuses first). A new lint test (`tests/config-registry.test.ts`, mirroring `tests/flagless-gh.test.ts`) fails CI if a script reads a frontmatter key with no matching registry entry, so a flag can never ship invisibly again the way `nudge_todowrite` did. Command count 26 → 27. See `docs/plans/2026-07-10-feat-discoverable-config-surface-plan.md` (#91) for the full design, including the deliberately-deferred Phase 2 (build-time aggregation of config flags across every plugin in this marketplace, once a second plugin ships one).

## [3.8.0] - 2026-07-10

### Added

- **`land-docs` skill — the autonomous "data lane" that ships compounded knowledge as its own docs-only PR and merges it on green, so a session closes out without a second user turn.** Before this, the seam between `land-pr` (merges the code PR) and `/workflows:compound` (writes `docs/solutions/**` markdown) had a gap: `compound` never touched git — it wrote the knowledge into the post-merge default branch's working tree, stamped the board `compounded`, and stopped on a blocking "What's next?" menu. The knowledge was left uncommitted and the agent turned back to ask the user what to do — another cycle before the session could end. `land-docs` closes that seam: it opens a `docs/<N>-knowledge` PR, follows its GitHub Actions checks (CI owns review — the skill runs no in-agent review pass), and **merges on green with no user turn; fixes a simple check failure; or pauses only when a failure genuinely warrants user input.** Its one safety property is a **docs-only scope gate** — every changed path must match `*.md` / `docs/**`; any non-doc path aborts the auto-merge and escalates — which is what licenses the unattended merge. Wired into `/workflows:compound` (new Phase 3) and `/workflows:orchestrate` (new Compound sub-row + suppressed the blocking `compound-docs` decision menu on the pipeline path), and referenced from the `land-pr` skill as the counterpart knowledge-PR lander. Skills 26 → 27.

## [3.7.0] - 2026-07-09

### Added

- **`nudge-todowrite-to-tracker.py` — optional, non-blocking `PreToolUse` (TodoWrite) hook nudging toward the repo's durable issue tracker.** `TodoWrite` is ephemeral, in-session scratch; a repo that has committed to a durable tracker (GitHub Issues / GitHub Project board) wants cross-session work filed there instead, without fighting `TodoWrite`'s legitimate ephemeral role with a hard block. The hook is silent (`exit 0`, no output) unless the repo opts in with `nudge_todowrite: true` in `agentic-engineering.local.md` frontmatter (same tracked-file security invariant as `issue_tracker:` — a committed copy is ignored) *and* a tracker actually resolves to something other than `none`. Tracker resolution reuses `workflow-repo-preflight.py`'s `resolve_issue_tracker()` chain verbatim (local override > committed board config -> `github-project` -> `gh auth` -> `github` -> `none`), so the reminder always names the same tracker the rest of the lifecycle tooling agrees on; beads is intentionally not a nudge target since the unified lifecycle already demotes it to a non-authoritative scratchpad (`plan-tracker-guard.py`). Pinned by `nudge_todowrite_to_tracker_test.py`. Addresses #89. No component count changes — hook addition only.

## [3.6.2] - 2026-07-09

### Added

- **`setup` skill now offers an opt-in up-front Headroom install (Step 3.8).** Previously the `headroom` skill only installed the CLI lazily on its first invocation; the plugin's setup flow did not manage it. Setup now detects install state (`command -v headroom`) and the available installer (`uv` preferred, `pip` fallback), and — only when Headroom is absent and an installer exists — offers `uv tool install "headroom-ai[all]"` behind an AskUserQuestion gate, then verifies with `headroom doctor`. Consistent with the plugin's norm of never installing a binary without consent: it skips silently when already installed, declines to offer when neither `uv` nor `pip` is present (pointing at the skill instead), never auto-installs on non-interactive runs (prints the command for later), and notes the AVX2/ONNX `[all]`-extra caveat with the base-package fallback. Step 5's confirmation summary gains a `Headroom:` line; the skill description is updated to match. Skill enhancement only — no component count changes.

## [3.6.1] - 2026-07-09

### Fixed

- **`block-no-verify` and `prevent-main-commit` hooks no longer false-block on PR-body prose.** Two precision bugs surfaced when authoring PRs from an agent shell: (1) `block-no-verify` scanned quoted strings but not **here-document bodies**, so a PR/issue body describing the bypass flag — e.g. `gh pr create --body-file - <<'EOF' … git commit --no-verify … EOF` — was blocked; `sanitize()` now strips heredoc bodies (per-heredoc backref, non-greedy) before matching, while a real bypass chained *after* a heredoc still blocks. (2) `prevent-main-commit` scanned the whole compound command for a `main`/`master` refspec token, so a `main` in a **sibling segment** (`git push -u origin my-feature && gh pr create --base main`, or a chained `git log origin/main`) false-blocked the push; the protected-refspec check is now scoped to the actual `git push` segment(s). Both fixes are pinned by expanded `block_no_verify_test.py` (heredoc cases) and `prevent_main_commit_test.py` (sibling-segment cases). No component count changes — hook precision only.

## [3.6.0] - 2026-07-09

### Added

- **`headroom` skill — AI context compression via the [Headroom](https://github.com/headroomlabs-ai/headroom) CLI.** Headroom compresses everything an agent reads (tool outputs, logs, RAG chunks, files, conversation history) before it reaches the LLM, cutting 60-95% of tokens with the same answers via reversible compression that caches and restores originals on demand. The skill follows the same shape as the `rclone` skill: a setup check that installs the tool as a global CLI with `uv tool install "headroom-ai[all]"` (pip fallback, plus AVX2/ONNX requirement notes and `headroom doctor` routing verification), a command reference (`wrap`, `proxy`, `perf`, `dashboard`, `learn`), and worked workflows for the three integration modes — wrapping a coding agent (`headroom wrap claude`), running the drop-in proxy (`headroom proxy --port 8787`), and library use (`from headroom import compress`). `headroom learn` (mine failed sessions into local markdown corrections) ties into the compounding-engineering loop. Skill count 25 → 26.

## [3.5.7] - 2026-07-08

### Changed

- **Removed ultrathink invocations from the workflow commands.** `/workflows:review` no longer frames its deep-dive phases as "ultra-thinking": the section-4 heading is now "Deep Dive Phases", the `<ultrathink_instruction>` block is a plain `<instruction>` (dropping "spend maximum cognitive effort"), the two `ULTRA-THINK:` thinking-prompt prefixes are gone, and the command description/`command_purpose` read "multi-agent analysis and worktrees". `/workflows:plan`'s closing note no longer gates `/deepen-plan` on "ultrathink enabled" — it now recommends running `/deepen-plan` for maximum depth unconditionally. Landing-page and generated command-reference copy updated to match. Behavior is unchanged; the commands relied on prose "ultrathink" cues rather than any harness feature. No component count changes.

## [3.5.6] - 2026-07-08

### Added

- **`git-worktree` skill gains a non-interactive `gc` subcommand for safe, unattended reaping of merged worktrees** (adapted from the `bluestar-intel` repo's post-merge `gc-worktrees.sh` hook). The skill previously only offered `cleanup`, which is interactive (`read -r` prompt — unusable in an agentic loop or hook) and force-removes EVERY inactive worktree regardless of merge state, so it can silently discard unmerged parallel work and leaves orphaned local branches behind. This is a real hazard for the plugin's core parallel/swarm workflows (`/resolve_parallel`, `orchestrating-swarms`), where several worktrees hold live in-progress work at once. `worktree-manager.sh gc [base-branch]` reaps a worktree only when ALL hold: it lives under `.worktrees/`, is not the current worktree, has a clean tree, is fully merged into the base (`git cherry` shows zero `+` commits and ≥1 `-` — patch-equivalence catches GitHub's default squash/rebase merges where SHAs differ, while a brand-new empty branch is left alone), and has been idle for the grace window (default 30 min, `WORKTREE_GC_GRACE_MIN`); it also deletes the now-orphaned local branch. `WORKTREE_GC=0` skips, `WORKTREE_GC_BASE` sets the default base (`origin/main` → local `main` fallback), and it always exits 0 so it can be wired into a git `post-merge` hook without ever failing the surrounding operation. `cleanup` is unchanged but now documents its force-remove hazard and points at `gc` for unattended use. Verified end-to-end in scratch repos: squash-merged worktree + branch reaped; genuinely-unmerged, dirty, and current worktrees all preserved. No component count changes — skill enhancement only.

## [3.5.5] - 2026-07-07

### Added

- **`docs/pages/changelog.html` is now generated from this file** (issue #78). The published docs-site changelog had silently diverged from `CHANGELOG.md`: hand-maintained from v1.0.0 → v2.6.0, it received two more hand-written entries at v2.32.1/v2.32.2 and was then untouched while ~30 releases (3.0.0 → 3.5.4) shipped — and nothing caught the drift, since `scripts/generate-docs.ts` deliberately left it as hand-written chrome. `scripts/generate-docs.ts` now parses this file (Keep a Changelog format: `## [x.y.z] - date` headers, `### Category` sections, single/nested bullet lists, inline bold/code/link spans, one summary table) with a small hand-rolled renderer — no new dependency; a markdown library was surveyed and rejected because the target page's per-category HTML/CSS wrapping (`.changelog-category.added/.changed/.fixed/…`, FA icons, version badges) needs bespoke mapping a generic renderer wouldn't produce anyway — and splices the result into `docs/pages/changelog.html` between the standard `<!-- GENERATED -->` markers, wired into the existing `bun run docs:build` / `docs:check` pipeline (`tests/docs-generated.test.ts` now covers the changelog page too, so drift is caught in CI like every other reference page).
- **Backfilled v1.0.0 → v2.6.0 into `CHANGELOG.md`** — this file previously started at v2.15.0; those 13 earlier releases existed only in the hand-written HTML. Transcribed verbatim (all agents/commands/skills, the v2.0.0 summary table, nested Puppeteer→Playwright migration list) so the generated changelog page loses no history switching to `CHANGELOG.md` as its sole source of truth.
- **Root `CLAUDE.md` "Keeping Docs Up-to-Date" section corrected** — no longer claims `changelog.html` "mirrors `CHANGELOG.md`" as a manual step; documents the generator relationship and warns against hand-editing the generated entries.

### Fixed

- **Orphan v2.32.1 / v2.32.2 HTML-only entries dropped, not migrated.** Both duplicated changes already recorded under `CHANGELOG.md`'s `[2.33.0]` entry (the `/release-docs` relocation and the `learnings-researcher` addition to `/workflows:review`) — hand-edited into the docs page as their own versions at some point but never given their own `CHANGELOG.md` entries. Generating from `CHANGELOG.md` naturally resolves the contradiction the issue flagged (HTML documented v2.32.1/v2.32.2 while `CHANGELOG.md` only had `[2.32.0]`) without double-recording the same change under two version numbers. No agent/command/skill/MCP changes — counts unchanged.

## [3.5.4] - 2026-07-07

### Added

- **`tests/setup-recipe.test.ts` — the setup skill's Step 4.5 gitignore recipe is now executed in CI, not just published** (todo 004 from the PR #72 review synthesis; the durability follow-up that PR deferred). The recipe's flags are load-bearing and lived only in markdown, unguarded by the count/frontmatter tests — the exact false-confidence shape docs/solutions/testing-patterns/recorded-fixtures-must-be-load-bearing.md warns about. The test extracts the first fenced bash block after the `## Step 4.5` heading **verbatim** (failing if the heading or block is missing, so doc and test cannot drift — a "simplified" recipe runs as simplified and fails on behavior) and executes it via `bash` in hermetic temp git repos (isolated `GIT_CONFIG_GLOBAL`/`GIT_CONFIG_NOSYSTEM`/`GIT_CEILING_DIRECTORIES`, so a developer's own excludes can't fake a pass) across the six core scenarios: fresh repo run from a subdirectory (entry lands in the **root** `.gitignore`; file ignored and untracked), legacy tracked copy (`tracked=1` detected, entry appended exactly once across a re-run — pinning `--no-index`, without which a tracked path is never reported ignored and every re-run would re-append; the test also asserts plain `check-ignore` fails where `--no-index` passes), pre-existing broader `*.local.md` pattern (byte-identical `.gitignore`, nothing appended), `.gitignore` without a trailing newline (the `tail -c1` repair keeps the last existing pattern intact), non-git directory (silent skip, `root=none`, no `.gitignore` created), and symlinked `.gitignore` (append refused — the PR #72 review guard — link target byte-identical across two runs). The echoed `root=/gitignore=/tracked=` status line is asserted exactly: the SKILL declares it the recipe's only observable output, consumed by the untrack consent gate and Step 5. Mutation-verified before landing: dropping `--no-index`, disabling the symlink guard, or renaming the heading each fails the suite. Also commits `todos/004` (pending → complete). No component changes — counts unchanged.

## [3.5.3] - 2026-07-07

### Fixed

- **`setup` now gitignores `agentic-engineering.local.md` on write and detects an already-tracked copy** (issue #62). The skill wrote per-machine config into the user's repo with no `.gitignore` handling, so a `git add .` committed it — exactly what the runtime forbids: `lifecycle_board.py` ignores a *tracked* `.local.md` as a security invariant and warns on every invocation, silently dropping the file's overrides. New Step 4.5 idempotently ensures the ignore entry — gated on `git check-ignore -q --no-index` (the skill's recipe notes explain why `--no-index` is load-bearing) — guards the append against a missing trailing newline, refuses to write through a symlinked `.gitignore`, and reports every outcome on a single echoed status line that the untrack consent gate and Step 5 confirmation consume, then detects a tracked copy (the same `git ls-files --error-unmatch` check the runtime's `_is_tracked` uses) and offers a consent-gated `git rm --cached` with the staged-deletion consequences spelled out. The full recipe also runs in Step 1 for existing configs, because legacy repos committed the file *before* any ignore entry existed and an entry alone never untracks it. All git operations anchor to `git rev-parse --show-toplevel`; non-git directories skip silently; the append is autonomous but untracking is never auto-run non-interactively. Live-verified in scratch repos (fresh, legacy-tracked with re-run, broader-pattern, no-trailing-newline, non-git). Skill instruction change only — no Python changes; component counts unchanged.

## [3.5.2] - 2026-07-07

### Fixed

- **`git-worktree` skill: `ensure_gitignore()` upgraded to the plugin's canonical gitignore idiom** (the setup skill's Step 4.5 recipe). The old exact-line gate (`grep -q "^\.worktrees$"`) plus bare `echo >>` had two defects: appending to a `.gitignore` that lacks a final newline concatenated `.worktrees` onto the last existing pattern (corrupting both entries), and the exact-line grep missed broader/equivalent patterns (`.worktrees/`, wildcards, other ignore sources), appending a redundant line. Now gates on `git -C "$GIT_ROOT" check-ignore -q --no-index .worktrees` (honors every ignore source and pattern form; `--no-index` is load-bearing — a tracked path is never reported ignored, so without it a legacy tracked `.worktrees` would re-append forever) and repairs a missing trailing newline via the `tail -c1` guard before a `printf` append. The guard chain's short-circuit is `set -e`-safe (a non-final `&&` failure doesn't trip it, and the chain is never the function's last statement) — verified against missing/empty/no-trailing-newline/pattern-variant `.gitignore` fixtures. No component changes — counts unchanged.

## [3.5.1] - 2026-07-07

### Fixed

- **A git-tracked `agentic-engineering.local.md` can no longer pin the issue tracker** — closes the gap the issue #62 plan deferred as out of scope. `lifecycle_board.py` already ignores a *tracked* `.local.md` for board identity and binding config (a tracked file rides PRs, so honoring it would let a PR redirect the lifecycle), but `workflow-repo-preflight.py`'s `read_local_config_tracker` still read `issue_tracker:` from a tracked copy — so a PR could commit `issue_tracker: none` and silently downgrade every workflow command out of board gating. The preflight now applies the same gate (`git ls-files --error-unmatch`): a tracked `.local.md` is skipped with a stderr warning and resolution falls back to auto-detect. Untracked (gitignored) overrides and invalid-value surfacing are unchanged; unit tests mirror `lifecycle_board_test`'s `test_tracked_local_config_is_ignored`.

## [3.5.0] - 2026-07-07

### Added

- **`block-slack-webhook` secret-hygiene guard hook, ported from `agent-leverage`** (PreToolUse — Bash + Write/Edit/MultiEdit, wired in `plugin.json`, with a unit test). Completes the agent-leverage guard cluster: the prior ports (`block-no-verify`, `prevent-main-commit`, `check-node-version`, `block-beads-jsonl-stage`) cover git and env hygiene, but the plugin had **no guard against committing a live secret**. A Slack incoming-webhook URL (`hooks.slack.com/services/...`) is a credential; hardcoding one into code, CI config, or a `curl` leaks it into git history and build logs. The hook blocks that on the unambiguous host+path — so the Slack *app* (`api.slack.com` / `chat.postMessage` / MCP tooling) is never blocked — and exempts prose (`.md`/`.mdx`/`.txt`/…) and files under `hooks/`/`scripts/` that merely *describe* the anti-pattern. The block message points to the correct alternative: read the webhook from an env var / secret manager, or send through a connected Slack app. Generalized from agent-leverage's repo-specific version (removed references to that repo's internal notification code paths). No new agents/commands/skills — counts unchanged.

## [3.4.0] - 2026-07-07

### Added

- **Bootstrap scaffolds the `actions/add-to-project` workflow when forward binding is `auto-add`** (issue #63) — the mechanism that makes #64's `auto-add` choice functional and flips `/lifecycle-doctor`'s `board_forward_binding` check from WARN to PASS. The built-in Projects v2 auto-add workflow has no create/enable API (`ProjectV2Workflow` is delete-only); the official `actions/add-to-project` Action reproduces it. When (and only when) the operator chooses `auto-add`, `bootstrap_lifecycle_board.py` writes `.github/workflows/add-to-project.yml` — **idempotent** (never clobbers an existing file) and **non-fatal** (a write failure degrades to a summary warning), mirroring the `link_repo` step. The scaffolded workflow is **hardened** per a security + framework-docs deepening pass: **SHA-pinned** `actions/add-to-project` (resolved live at scaffold time via `gh api repos/actions/add-to-project/commits/v2`, falling back to a known-good constant — a moving `@v2` tag would run with the `ADD_TO_PROJECT_PAT` secret in scope, the tj-actions/changed-files compromise class, amplified across every scaffolded repo; first-party `actions/*` is no exemption), `permissions: {}` at top **and** job level (the PAT does the Projects write, so `GITHUB_TOKEN` needs nothing — stricter than `contents: read`), `on: issues: [opened]` with no untrusted checkout and no `run:` steps, plus an inline comment forbidding future `run:` steps that interpolate `github.event.issue.*` (script-injection guardrail). Bootstrap also scaffolds `.github/dependabot.yml` (github-actions ecosystem) so the pin stays current — created only when absent; an existing dependabot config is never parsed/merged (a warning points the operator to add the ecosystem). The correct `users/` vs `orgs/` project-url segment is resolved via `gh api users/<owner> --jq .type`. The one remaining manual step — the `ADD_TO_PROJECT_PAT` secret — is documented least-privilege-first (fine-grained PAT with org Projects:R/W + repo Issues/PRs:read → GitHub App token → classic PAT fallback). No new agents/commands/skills — counts unchanged.

## [3.3.0] - 2026-07-06

### Added

- **The repo→board binding is now an explicit, recorded decision** (issue #64). Bootstrap used to leave "configure auto-add" as an orphaned manual UI step with no explanation and a doctor check that could only say "verify by hand." Projects v2 boards are *materialized collections, not live queries* — creating an issue does not put it on any board, and GitHub's auto-add is **forward-only** (never backfills). Setup now records **two orthogonal decisions**, treated independently (backfill is offered under *any* forward choice, never gated behind auto-add):
  - **(A) Forward binding — how NEW issues reach the board.** `bootstrap_lifecycle_board.py` gained `--forward-binding {workflow-only,auto-add,none}` (default `workflow-only`), written into committed `agentic-engineering.md` as `github_project_forward_binding` **in the same write as board identity** (a crash can never leave identity without policy). Omitting the flag **preserves a prior choice on re-run** rather than resetting it. `/lifecycle-doctor` replaces its uncheckable "verify by hand" line with a concrete per-branch `board_forward_binding` check: `workflow-only` PASSes when no orphaned auto-add workflow exists; `auto-add` verifies `.github/workflows/add-to-project.yml` is present and the board is repo-linked (its token secret is write-only, so that one bit is explicitly called out as unverifiable); `none` is informational; an unrecognized/unrecorded value WARNs. (The auto-add workflow *scaffolding* itself remains issue #63's mechanism — this change records and verifies the decision.)
  - **(B) Backfill — put EXISTING issues on the board now.** New `lifecycle_board.py --backfill` verb: a one-time, idempotent add of every open origin-repo issue not already on the board, recording a `github_project_backfilled_through` high-water mark so a re-run adds only what a partial run missed. Enumerates **repo issues via paginated `gh issue list`** — deliberately *not* the 50-capped ready-work path, which would have silently dropped issues 51+ — excludes PRs and closed issues, dedupes against board membership with one read (not N+1), tolerates partial failure (one failed add never aborts the loop), and advances an advisory high-water marker only over a failure-free prefix (the marker gates whether setup re-offers the backfill; a re-run always recomputes the full open-vs-board difference). Never run by bootstrap, so setup never mutates issues onto the board unattended (CI-safe by construction).
  - Internals: the committed-config writer (`upsert_frontmatter_keys` / `write_config_keys`) moved to `lifecycle_board.py` as the single write path shared by bootstrap and the backfill marker; the forward-binding doctor verdict is a pure, unit-tested helper (`evaluate_forward_binding_check`). No new agents/commands/skills — counts unchanged.

## [3.2.0] - 2026-07-06

### Removed

- **`/lfg` and `/slfg` commands, and every reference to the optional `ralph-wiggum` continuation loop.** The two straight-line "run these commands in order, don't stop" chains duplicated what `/workflows:orchestrate` already does as a proper reviewer-driven loop, and `ralph-wiggum` was an unbundled external dependency the pipeline leaned on for don't-stop-early behavior. Doubling down on the `/workflows:*` commands as the single autonomy surface: `/workflows:orchestrate --auto` is now the fully-autonomous entry point. Purged the references from `orchestrate.md`, `land-pr`, `merge.md`, `plan.md`, `FLOWS.md`, and both READMEs. Counts: 28→26 commands.

### Changed

- **`/workflows:orchestrate` is now fully autonomous by default.** The default runs the whole pipeline to a merge with **no approval prompts of any kind** — self-answering every intermediate judgment call, merging once the PR is landable, and surfacing *only* genuine blockers (material scope change, branch protection, unresolvable ambiguity). Material scope expansion (redefining WHAT is built) is treated as a genuine blocker, so it still stops the run — that blocker-only floor holds identically in every mode. Added a new **`--final-review`** flag for the same hands-off run with one reinstated pre-merge gate (presents the review packet and waits for your go). The old "delegate pauses once at Final-Review" behavior is now `--final-review`; the old `--auto` is folded into the default (and accepted as an explicit alias). The autonomy dial reads `--careful` > `--steer` > `--final-review` > default (fully autonomous).
- **The independent `/workflows:review` stage is now explicitly non-skippable in every mode**, including `--auto`. Hardened `land-pr` condition 3 from "the caller's responsibility" to a self-satisfying gate: `land-pr` confirms a review ran this cycle and, if it cannot, runs `/workflows:review` (with fresh reviewer sub-agents) and resolves P1s **before** any merge — a PR is never merged unreviewed. Clarified in `/workflows:work` that its optional inline reviewer agents are an in-session pre-check, never a substitute for that stage.

### Added

- **Uniform run-level no-progress stop.** Replaced the scattered per-stage "~2 attempts" prose with one stagnation mechanism at the orchestrate loop level: a pass makes *progress* only if the board stage advanced or one of {open sub-issues, unresolved review threads, failing required CI checks, open P1 findings} strictly decreased; two consecutive no-progress passes at a stage enters a new `stalled` terminal state and escalates with evidence. Evidence-based, not a clock/iteration/token cap. The existing `land-pr` and `/workflows:work` retries are now documented as instances of this one rule (a retry that shrinks nothing counts toward the bound).

## [3.1.0] - 2026-07-06

### Added

- **`verification-loop` skill — a systematic verify-before-done pass.** Runs build → types → lint → tests → security → diff review as sequential gates and ends with a single ready / not-ready verdict. Adopted from `affaan-m/ECC` as the **first upstream adoption** executed through the `/upstream-scan` triage pipeline (landed via PR #35, issue #60). Counts: 24→25 skills.
- **Two operational guard hooks ported from `agent-leverage`** (PreToolUse/Bash, wired in `plugin.json`), each shipping a unit test: `check-node-version` blocks package-manager commands when the active `node` major differs from the project's declared requirement (`.nvmrc` / `engines.node`), no-op for non-Node projects (PR #27, issue #56); `block-beads-jsonl-stage` blocks staging the passive `.beads/*.jsonl` Beads export so the local scratchpad never lands in git (PR #38, issue #57).
- **Test coverage + a hook catalog for the existing safety hooks.** Added unit tests for `block-no-verify` and `prevent-main-commit` (ported in a prior release without tests) and a `scripts/HOOKS.md` index documenting every plugin hook (PR #37, issue #59).
- **Bootstrap now links the lifecycle board to its origin repo.** Projects v2 boards are owned by a user/org and can only be _linked_ to a repo — there is no repo-owned board — and linking is what surfaces the board on the repo's **Projects** tab and enables auto-add-from-repo. `bootstrap_lifecycle_board.py` gained a `link_repo` step (after workflow config, before the committed-config write) that is **idempotent** (queries current links via a shared `lifecycle_board.project_linked_repos` helper and skips the mutation when already linked) and **non-fatal** (a link failure degrades to a summary warning, never an abort — board resolution only needs `owner`+`number`). `/lifecycle-doctor` gained a matching `board_repo_link` check under Board schema: PASS when linked, WARN with the exact `gh project link …` fix when not, SKIP when unreadable. This closes the gap where a freshly bootstrapped board was invisible on the repo's Projects tab, which read as "no board" in the multi-repo/multi-customer model. Related footgun this surfaces: the committed `agentic-engineering.md` records one board's `owner`/`number`, so a fork/clone under a different owner must re-run bootstrap to point at _its own_ board.

### Removed

- **npm distribution of the converter CLI.** The `@aagnone3/agentic-plugin` package was never successfully published (the advertised `bunx` command had never worked), and GitHub alone distributes everything: the plugin via the git-based marketplace, the CLI via `npx github:aagnone3/agentic-engineering` (pinnable to a release tag). Deleted `publish.yml`, marked `package.json` private (hard-prevents accidental registry publishes), and updated the README install instructions. Unused distribution surface is untested surface — same doctrine as the 3.0.0 Linear removal.

## [3.0.0] - 2026-07-06

### Added

- **`operating-principles` skill — how to operate, distilled from Claude Fable 5 for executor models.** The general operating approach for engineering work, captured as explicit procedure so Opus-tier executors (the implementation tier in delegate-mode orchestration) can follow a frontier model's policy mechanically. Depth is self-calibrating: a Step-0 gate sends easy tasks down a light path (do, verify once, report) and multi-step / ambiguous / expensive ones through the full procedure — ground-truth-before-planning (goal restated as an observable acceptance check, real code read before decomposition, load-bearing assumptions verified cheapest-first), risk-first decomposition where every subtask has an independently checkable exit condition, an explicit goal → evidence → gap → action execution loop with a two-strike backtrack rule (two failed fixes at one point = wrong mental model, go instrument) and a blocked-state taxonomy (self-serve facts; escalate only genuine decisions), independent-channel verification (execute > trace > hostile diff read > sibling sweep, plus the make-it-fail-once and green-is-real anti-theater disciplines), and calibrated reporting (every claim labeled Verified / Checked / Assumed; "should work" never rounds up to "works"). Progressive disclosure in four layers: an **always-on CLAUDE.md snippet** (`assets/claude-md-snippet.md` — the ten compressed rules plus a trigger line pointing at the skill, paste-ready for consumer repos), the SKILL.md spine, and three depth references — `decomposition-patterns.md` (load-bearing-question-first, vertical slice, interface-first, spike-then-implement, checkpoint-before-irreversible, scope ledger + five anti-patterns), `verification-playbook.md` (per-artifact checklists for bug fix / feature / refactor / migration / config), and `failure-modes.md` (14 characteristic agent failure modes — success theater, patch spiral, imagined codebase, scope drift, premature done, stopping-at-a-plan, … — each with a detection signal and countermeasure). Wired into the delegation path so it is used constantly, not on request: `/workflows:work` loads it at entry and its subagent brief template instructs every implementation sub-agent to follow it; `/workflows:orchestrate` inherits both via that template and applies the same discipline to its own review-and-steering loop; and the `setup` skill gains Step 3.7, which offers to install the snippet into the consuming repo's existing `CLAUDE.md` and/or `AGENTS.md` — a marker-guarded append (`operating-principles always-on layer`) that is idempotent across re-runs and symlink-safe, with an offer to create `CLAUDE.md` when neither file exists. Counts: 23→24 skills.
- **Unified work-item lifecycle on a GitHub Projects v2 board** (part 2 of the unified-lifecycle work, issue #39). Replaces the three-tracker dispatch model with a single lifecycle — `stub → brainstormed → planned → in_progress → in_review → shipped`, with order-independent terminal refinements `deployed` / `compounded` and the `abandoned` off-ramp — whose source of truth is a GitHub Projects v2 board readable and writable by both humans (browser) and agents (`gh` CLI). New `scripts/lifecycle_board.py` (importable, stdlib-only, pure decision core + injected `run_gh`) exposes the verbs `--gate` / `--claim` / `--set-status` / `--ready-work` / `--reconcile` / `--doctor` with a uniform `{ok, error_code, error, fix}` error contract; its reconciler applies a **closed set of five repairs** (`merged_close_missed`, `not_planned_close`, `pr_closed_unmerged`, `abandoned_cascade`, `pr_reopened`) plus three report-only flags (`merged_to_non_default_branch`, `stale_join_key`, `truncated_ready_work`), never widening past five. Every workflow command gains an idempotent **entry gate** (`--gate`) that reads lifecycle state and routes on a closed verdict enum, plus a one-line **writer contract** naming the single transition it owns. A new `skills/lifecycle/SKILL.md` holds the shared vocabulary (9 stages, writer table, claim semantics, security invariants) with a `references/gh-recipes.md` for the concrete `gh` invocations, deploy adapter, and git-flow issue-closer workflow. A **bootstrap script** (hosted by the `setup` skill) creates and configures the board via ID-preserving `updateProjectV2Field` — a fresh-project guard refuses to adopt a customized project, and the "Item reopened" workflow is disabled **if present** (new projects typically don't ship it; `/lifecycle-doctor` re-checks) so that where present, reopening never re-stamps `stub`. Board identity moves to **committed** config (`github_project_owner:` / `github_project_number:` in `agentic-engineering.md`) resolved from the git common dir so worktree-isolated subagents behave identically; only the session TTL cache stays local. New **`/lifecycle-doctor`** command (wrapping `--doctor`) is the setup verification front door: a PASS/WARN/FAIL/SKIP checklist over toolchain, repo shape, board schema, and delivery topology, ending with "Ready for first work item: yes/no" (`--live` runs the end-to-end scratch-issue probe). The fork-trap hook (`block-upstream-pr.sh`) is extended to cover `gh project` writes, ProjectV2-mutation GraphQL, `GH_REPO=` prefixes, and REST writes to upstream paths, backed by a committed `tests/flagless-gh.test.ts`. **`gh` ≥ 2.94.0 with the `project` scope is now a hard prerequisite** (`--parent`, `--blocked-by`, dependency JSON fields), pinned in CI. Counts: 27→28 commands, 22→23 skills (new `lifecycle-doctor` command; new `lifecycle` skill offsets the deleted `linear-sync`).

### Removed

- **BREAKING: Linear support removed entirely** (part 1 of the unified-lifecycle work, issue #39). Deleted the four `/linear:*` commands (`sync`, `status`, `import`, `pull`), the `linear-sync` skill, and the `agentic-plugin linear` CLI (~1,650 lines of TypeScript: `src/commands/linear.ts`, `src/sync/linear.ts`, `src/sync/linear-api.ts`, `src/types/linear.ts`). The issue-tracker resolution chain is now `beads | github | none` — `LINEAR_API_KEY` is no longer consulted, the `issue_tracker_ambiguous` / `linear_api_key_present` preflight fields are gone, and `linear_issue:` is no longer accepted by the plan-tracker-guard Stop hook (use `bead_id:` or `github_issue:`). Todo-file frontmatter drops `linear_id` / `linear_synced_at`. Every workflow command's Linear dispatch branch (work, plan, review, triage, resolve_todo_parallel, land-pr, setup, file-todos, merge) was removed rather than deprecated: unused dispatch branches are untested surface where faithfulness dies silently. Migration: existing plans with `linear_issue:` frontmatter should add a `github_issue:` (or `bead_id:`) on next touch; git history is the archive if Linear support is ever needed as a companion plugin. Counts: 31→27 commands, 23→22 skills.

### Changed

- **Issue-tracker resolution is now `github-project | github | none`** (beads left the chain). `github-project` is selected when a committed board config is present and unlocks the full lifecycle machinery; `github` is plain issues + file-todos (today's semantics, no board writes); `none` degrades further. Beads is demoted to an opt-in, non-authoritative implementer scratchpad — `bd remember` still works, but no gate ever reads a bead and nothing syncs.
- **`/workflows:work` no longer closes the issue at PR creation.** Phase 4 opens the PR with `Closes #N` and sets Status=`in_review`; the built-in "Item closed" merge automation is the sole writer of `shipped`. The previous "PR creation is the completion event" rationale is replaced by automation-owns-shipped. `/workflows:review` records findings via a single `todos/*.md` file-todos path (the beads findings branch was removed).
- **`/workflows:orchestrate` — delegate mode is the new default: the orchestrator delegates to sub-agents, reviews their work, and surfaces only blockers + one final review.** The orchestrator (running on the session's strongest model) no longer implements feature code inline by default. It dispatches every work item to a focused implementation sub-agent (Opus-tier, background, parallel when file-disjoint, per `/workflows:work`'s Orchestrated Execution) and performs the accept/retry/escalate review of each returned diff itself. The intermediate judgment gates are self-answered and recorded in a **decision log**: approach selection takes the brainstorm's recommendation (product-shaping forks still escalate), the Plan-Approval gate becomes a **plan self-review** (`document-review` + `spec-flow-analyzer`), and findings triage resolves to fix-P2s/defer-P3s. The run pauses exactly twice at most: genuine blockers (batched, any time) and the new **Final-Review gate** — a pre-merge packet with what was built, review/verification results, sub-agent stats, and the replayed decision log, offering merge / review-first / request-changes / don't-merge. Material scope expansion still escalates in every mode. The previous default cadence lives on as `--steer` (approach, plan-approval, triage, and merge checkpoints); `--auto` is demoted from a mode to a **modifier on delegate mode** — it toggles exactly one bit, collapsing the Final-Review gate (auto-merge once landable, packet becomes the final summary; for unattended runs), and its former non-negotiable Plan-Approval stop is replaced by the plan self-review; `--careful` is unchanged. The `--auto` spelling is kept so `land-pr`'s autonomous-context whitelist (`/lfg`, `/slfg`, `/workflows:orchestrate --auto`) is unaffected. `/workflows:work` documents the two hooks the orchestrator relies on: Orchestrated Execution is the default execution model under delegate mode, and its dispatch step now carries the model-tiering rule (implementation on Opus-tier subagents, review on the orchestrator's tier, mechanical chores cheaper). FLOWS.md's orchestrate diagram gains the land stage and Final-Review hexagon with per-mode gate annotations.

### Fixed

- **`plan-tracker-guard` now documents and tests dotted uppercase-prefix bead IDs.** The base-36 branch of `REAL_TRACKER_VALUE_RE` already accepts uppercase prefixes with a lowercase base-36 suffix (e.g. `AL-eh4`), but the dotted child-ID form `AL-xs7.3` — which exercises the `(?:\.[a-z0-9]+)*` segment tail — had no test coverage. Added a dedicated test for the dotted form and extended the accept test to cover `AL-eh4`, locking in that uppercase-prefix beads IDs (parent and child) pass while uppercase-suffix placeholders like `AL-NNN` stay rejected.

### Added

- **`/analyze-source` command — one-off evaluation of any external resource.** Given an X post, a blog, a GitHub repo, a marketplace, or an installable tool, the command resolves the resource (x.com via an `api.fxtwitter.com` → `cdn.syndication.twimg.com` → WebSearch fallback chain, following links to the canonical repo before classifying), triages it as a **technique** / **artifact repo** / **installable tool**, spends analysis depth proportional to that type (idea-vs-existing-components for a technique; a full `gh api` fact sheet — license/stars/dates/archived, trees-API structure, 2–3 credential-free component samples, overlap/gap vs the plugin inventory, and registry decision memory — for a repo; duplicate-vs-complement plus install security surface for a tool), and returns **exactly one** verdict: author locally, track as an upstream source (emitting a ready-to-paste `docs/upstream-sources.md` block + top cherry-pick candidates — the intake exit), spin up a new domain plugin, reference/install-alongside, or skip. Read-only by design (`disable-model-invocation`, scoped `allowed-tools` with no `Write`/`Edit`/`gh issue`/`gh pr`; all fetched content is untrusted data read in credential-free subagents) and explicitly delegation-friendly for background agents. Reframed from the originally-planned `/upstream-intake`: the general act is **analysis**, and registry intake is just one of five exits — validated by two real runs before implementation, the ECC analysis (verdict: track upstream) and the codex-plugin-cc X-post analysis (verdict: reference/install-alongside). From the 2026-07-03 plan (issue #31).
- **`/upstream-scan` invariant — fork-parent reads must not share a command line with a `gh issue`/`gh label` write.** The repo's fork-trap hook literal-matches the `EveryInc` parent slug anywhere in a command that also contains a write subcommand, so a compound line (`gh api repos/EveryInc/… && gh issue edit …`) is denied even though both halves are individually safe. Documented in the command's invariants as its own Bash-invocation rule (maiden-run finding from PR #33).
- **`/upstream-scan` command + upstream-source registry — recurring adoption from external repos.** A new registry (`docs/upstream-sources.md`, repo-level) records each upstream source (ECC, the EveryInc fork parent, agent-leverage) with its license, visibility, and per-component provenance (`adopted:`/`deferred:` entries carrying `upstream: path@sha` refs, reviewer, and date). The `/upstream-scan` command compares each source's current component inventory (GitHub trees API) against {local components, adopted, deferred}, evaluates candidates with a curated lens, checks adopted components for upstream drift, and reports to one long-lived, fully-regenerated GitHub issue per source — heartbeat line, evidence columns, and a ready-to-paste registry block for the triage PR. Fully parameterized via registry frontmatter (`report_repo`, `report_label`): zero repo names in the command. Safety: `disable-model-invocation`, scoped `allowed-tools` (no `Edit`, no `gh pr`), explicit `--repo` on every gh call, untrusted-content rules with credential-free evaluation subagents, and private-source redaction. Enforced by a new merge-time lint (`tests/upstream-registry.test.ts`): registry schema, entry grammar, and a flagless-gh regression guard. The repo's fork-trap hook (`block-upstream-pr.sh`) now also covers `gh issue` subcommands. From the 2026-07-02 upstream-adoption plan (issue #28); prior art: Renovate's dependency dashboard, cargo-vet audits, Chromium third-party metadata.
- **`/workflows:merge` command — a thin entry point to the `land-pr` skill.** Gives the pipeline a command-named merge step (`/workflows:merge [PR] [--auto]`) that delegates entirely to `land-pr` — no merge logic is reimplemented. Preserves the `/workflows:merge` ergonomics some workflows rely on while routing through the single landability/merge-gate implementation (CI wait, review-thread resolution via `resolve-pr-parallel`, independent-review gate, branch cleanup, idempotent tracker-item close across beads/Linear/GitHub).
- **`land-pr` skill — the completion-and-merge tail the pipeline was missing.** The plugin modeled `plan → work → (PR opened) → review → resolve comments` but had no single component that drives a PR the rest of the way: wait on CI, resolve every review thread (delegating to `resolve-pr-parallel`), confirm approval and mergeability, then **merge** and clean up (delete branch, fast-forward the local default branch, idempotently close the tracker item). It defines explicit landability conditions (CI green + threads resolved + approved/mergeable) and a **merge gate**: pause-and-ask by default, **auto-merge only in autonomous contexts** (`--auto`, or when called from `/lfg` / `/slfg` / `/workflows:orchestrate --auto`) and only once all three conditions hold. Ships a `scripts/pr-landable-status` helper that emits the gating signals as JSON. Wired into the workflow surface: `/lfg` and `/slfg` gain a land-and-merge step before `DONE`; `/workflows:orchestrate` gains a land stage in its pipeline diagram, decision table (the merge is a 🧍 CHECKPOINT in steer mode, AUTO in `--auto`), state-detection, and final summary; `/workflows:work` Phase 4 and `/workflows:review` now point to `land-pr` as the next step after PR creation / findings resolution.

- **Deterministic docs-site generator (`scripts/generate-docs.ts`, `bun run docs:build` / `docs:check`), gated in CI.** Replaces the manual `/release-docs` skill with a script that regenerates the reference pages (`docs/pages/agents|commands|skills|mcp-servers.html`) and the landing-page stat numbers directly from the plugin's components — card sections (between `<!-- GENERATED -->` markers) and each page's "On This Page" sidebar — preserving all hand-written page chrome. A new `tests/docs-generated.test.ts` (run by `bun test`) fails if the committed pages drift from the components, so the docs site can no longer fall out of sync. Regenerated all four reference pages, which had drifted badly (7 agents, 14 commands, 8 skills missing; stale counts; a removed Playwright MCP server still listed). `/release-docs` is now a thin wrapper around `bun run docs:build`.
- **Plugin consistency test (`tests/plugin-consistency.test.ts`), enforced in CI via `bun test`.** Asserts the filesystem truth (counts of agents/commands/skills, MCP servers) against every place those numbers and lists are declared — `plugin.json`, `marketplace.json`, both READMEs, and the `docs/index.html` landing-page stats — plus version parity between `plugin.json` and `marketplace.json`, README completeness (every command by frontmatter `name`, every agent, every skill must be documented), and frontmatter hygiene (every command/agent declares `name` + `description`; every skill's `name` matches its directory). This closes the "added a component but forgot to update X" gap that previously had to be caught by hand. Failure messages name the exact file/component out of sync.

### Fixed

- **`deploy-docs.yml` published a non-existent path** (`plugins/agentic-engineering/docs/`), so the GitHub Pages deploy never fired for the real site at root `docs/`. Corrected the trigger filter and upload path to `docs/`.
- **`docs/pages/mcp-servers.html`** still documented a Playwright MCP server that the plugin no longer bundles (config examples, requirements row, intro copy). Removed.
- **Plugin README command table was missing 3 commands** (`/deploy-docs`, `/agent-native-audit`) and listed a phantom `/xcode-test` instead of the real `/test-xcode` — the table claimed 27 commands but listed 26 (one wrong). Now complete and correct.
- **`resolve-pr-parallel` skill** declared `name: resolve_pr_parallel` (underscores), violating the rule that a skill's `name` must match its directory. Corrected to `resolve-pr-parallel`.

### Changed

- **`/workflows:work` — Orchestrated Execution is now tracker-driven (beads / Linear / file-todos), not beads-only.** The section is generalized from "delegate beads to subagents" to a tracker-agnostic model with a **Tracker bindings** table mapping the same lifecycle (list-ready → claim → close → block → add-follow-on) onto each tracker's verbs; the beads parent-vs-child and Phase-4 close rules are preserved as the beads-specific instantiation. Phase 2 gains an **execution-model selection table** (Inline / Orchestrated / Swarm) that applies to any tracker, the subagent brief is generalized to "one tracked issue," and `argument-hint` now signals that an issue/bead id can be passed directly. Ports the still-relevant idea from the stale `feat/work-orchestrated-bead-execution` branch onto current `main` (the branch's tracker-*detection* idea was already superseded by the preflight script).

### Added

- **`FLOWS.md` — visual reference for every workflow.** A plugin-root document with mermaid diagrams for each flow (`orchestrate`, `brainstorm`, `plan`, `deepen-plan`, `work`, `review`, `compound`, and the autonomous `lfg`/`slfg`), a shared shape legend (human checkpoints vs automatic steps), and a "big picture" composition diagram. Linked from `README.md`.
- **`/workflows:orchestrate` — a steering orchestrator over the full pipeline.** Drives `brainstorm → plan → [deepen-plan] → work → review → compound` autonomously, sitting between the user and the raw workflow commands like `/goal`/`/loop` sit over a task. It auto-handles every menial transition (branch setup, "proceed?" prompts, detail-level choices, tracker bookkeeping, running the next stage) and pauses **only at meaningful decision gates**: approach selection (during brainstorm), a non-negotiable **Plan-Approval gate** before any code is written, and **findings triage** after review (P1s are auto-fixed; the user decides on P2/P3). Includes an autonomy dial (`--auto` minimizes gates to plan-approval + blockers; default "steer"; `--careful` confirms at every stage boundary), artifact-driven **state detection** so re-running resumes in place, a sub-command auto-answer cheatsheet, and blocker-batching (one `AskUserQuestion`, not drip-fed). Has full operation parity with `/lfg`: the same finalization steps run automatically when applicable — `/resolve_todo_parallel` for approved findings, `/test-browser` for web/iOS E2E verification, and `/feature-video` to attach a walkthrough to the PR — plus the optional `ralph-wiggum` continuation loop (used only in `--auto` mode, and it never overrides a human gate). Contrast with `/lfg` (fully autonomous, no human in the loop): orchestrate runs the same operations but keeps the human at the steering wheel for the few decisions that shape the outcome.
- **`/workflows:work` — Orchestrated Execution style for the beads tracker.** A third execution style (alongside inline and Swarm) where the agent acts as orchestrator: it owns the bead state machine and delegates implementation to one focused subagent per bead, looping each bead to a terminal state (resolved or a verified blocker) before returning to the user. Works for a single bead or a whole set. Adds terminal-condition definitions, a wave-based dispatch procedure, a subagent brief template, parallelism/worktree rules, and discovered-work-as-follow-on handling — all aligned with the existing parent-vs-child close convention (child beads close in the loop; the parent/standalone bead closes in Phase 4 after the PR). Picked via an execution-style note in the Phase 2 beads block; contrasted with Swarm mode for when to use each.

### Changed

- **`/workflows:plan`** — tracker-issue creation is now a mandatory gate, not a post-action option. The command runs a new "Step 7. Create Tracker Issue" inline between `## Write Plan File` and `## Post-Generation Options`, and a precondition assertion re-verifies the plan frontmatter before any next-step menu is opened. The `Post-Generation Options` menu surfaces the tracker ID in its preamble and omits `/workflows:work` when the explicit `issue_tracker: none` carve-out is active. Closes context-eww.
- **Frontmatter templates** (MINIMAL/MORE/A LOT) now mark `bead_id` / `linear_issue` / `github_issue` as REQUIRED fields (exactly one) rather than optional `# added by /workflows:plan` annotations.

### Added

- **Stop hook safety net** (`scripts/plan-tracker-guard.py`, registered via `.claude-plugin/plugin.json` `hooks.Stop`) blocks turn termination when any plan file under `docs/plans/` modified in the current session lacks a tracker ID in its frontmatter. Respects `issue_tracker: none` carve-out and `stop_hook_active` re-entry protection. Catches any agent that bypasses or forks the `/workflows:plan` workflow.

### Removed

- The standalone `## Issue Creation` section at the bottom of `commands/workflows/plan.md` (content moved into mandatory Step 7).
- `Create Issue` option from Question 2 of `Post-Generation Options` (issue creation is now upstream of the menu).
- `You can also type freely — e.g., 'create issue'` hint from Question 1 (no longer reachable).

### Fixed

- **`/workflows:work` never closed a standalone bead.** Phase 4 closed `$PLAN_BEAD`, but for the standalone-bead flow (the common `bd ready` / explicit-bead-id case) Phase 1 never set `PLAN_BEAD` and there is usually no plan file for the `yq '.bead_id'` fallback — so the bead was never claimed *or* closed (`bd close ""` silently no-op'd), and Phase 2 ("Phase 1 set no `PLAN_BEAD`") contradicted Phase 4 ("the standalone bead claimed in Phase 1"). Phase 1 now establishes and claims `PLAN_BEAD` in both standalone and plan-with-children modes; Phase 4 suppresses the `yq` error when no plan file exists and guards against an empty id (fails loudly instead of closing nothing).

## [2.42.0] - 2026-06-29

### Added

- **`reflect-for-skill-updates` skill — the meta-improvement loop for compounding engineering.** Where `/workflows:compound` captures the *solution* to a technical problem, this skill captures *what was missing from the tooling or documentation that let the problem occur in the first place*. It provides a structured gap-analysis process: identify root cause → categorize (missing automation, incomplete skill, workflow gap, undocumented dependency) → implement the fix in the right place (SKILL.md, CLAUDE.md, hook, script) → verify the fix would have prevented the issue. Adapted from agent-leverage's operational toolchain; linked as a natural follow-on to `compound-docs`. Increases skill count to 23.

- **`/ci-resolve-workflow-issues` command — guided CI diagnostic workflow.** The plugin's `land-pr` skill waits for CI to be green before merging, but there was no guided workflow for _fixing_ a failing build. The new command walks through identifying the PR, fetching failure logs (via `gh` or GitHub MCP tools), classifying the failure type (lint, types, tests, build, E2E, lockfile, migration, environment), reproducing locally, applying the fix, verifying, and pushing — with a flaky-failure re-run shortcut and a reference table of `gh run` commands. Links to `land-pr` as the natural next step once checks pass.

- **`block-no-verify` PreToolUse hook** (`scripts/block-no-verify.py`). Registers via `plugin.json` `hooks.PreToolUse`. Blocks `git commit --no-verify` / `-n` and `git push --no-verify` in any project that installs this plugin. Uses segment-aware regex to avoid false positives on grep/echo commands that merely mention the flag. Pre-commit and pre-push hooks are the last local quality gate before CI — bypassing them breaks the compounding-quality chain the plugin is built on.

- **`prevent-main-commit` PreToolUse hook** (`scripts/prevent-main-commit.py`). Registers alongside `block-no-verify`. Blocks `git commit` while on `main`/`master` and any explicit `git push` that targets those branches. Enforces the plugin's PR-based workflow (plan → work → PR → review → merge) for all projects that install the plugin, preventing accidental direct pushes that bypass code review and CI.

## [2.38.0] - 2026-05-16

### Added

- **Beads (`bd`) as a first-class issue tracker** alongside Linear and GitHub. Workflow commands now resolve an `issue_tracker` value (`beads | linear | github | none`) at start and dispatch accordingly.
- **`agentic-engineering.local.md`** schema extended with `issue_tracker:` frontmatter field. Explicit override always wins over auto-detection.
- **Preflight script** (`scripts/workflow-repo-preflight.py`) now reports `beads_installed`, `beads_initialized`, `github_cli_authed`, `issue_tracker_resolved`, `issue_tracker_source`, `issue_tracker_ambiguous`, and `beads_remember_available`.
- **`/workflows:plan`** writes `bead_id:` into plan frontmatter when tracker is `beads`; otherwise still writes `linear_issue:` or creates a GitHub issue unchanged.
- **`/workflows:work`** uses `bd ready`/`bd update`/`bd close` instead of TodoWrite when tracker is `beads`. For `linear`/`github`/`none`, TodoWrite is preserved (no regression).
- **`/workflows:review`** creates findings as beads (`bd create … --tags=code-review`) instead of `todos/*.md` files when tracker is `beads`. The Linear push step (Step 2b) is now gated to run only when tracker is `linear`.
- **`/workflows:compound`** appends `bd remember "<insight>" --link "<solution-doc>"` whenever `bd` is on PATH, regardless of tracker. Complements (does not replace) the solution doc.
- **`/workflows:brainstorm`** offers an optional "Capture as bead" handoff step when tracker is `beads`, pre-seeding the parent bead for the eventual plan.
- **`setup` skill** writes the auto-detected `issue_tracker:` into the generated config and surfaces ambiguous detections via AskUserQuestion.

### Changed

- Auto-detect priority for `issue_tracker`: `.beads/ + bd` → `beads`, then `LINEAR_API_KEY` → `linear`, then `gh auth status` → `github`, else `none`. First match wins. Existing Linear users with `LINEAR_API_KEY` set and no `.beads/` are unaffected.
- Every workflow command prints a one-line tracker banner at start (e.g. `Tracker: beads (auto-detect)`). If both `.beads/` and `LINEAR_API_KEY` are present, the banner notes the ambiguity and points at the override.

### Preserved (no behavior change)

- All `agentic-plugin linear pull|push|create` calls fire unchanged when tracker is `linear`.
- `linear_issue:` frontmatter field is still written/read for Linear users.
- The `file-todos` skill path is still used for `todos/*.md` creation when tracker is `linear`/`github`/`none`.
- `/workflows:work` still uses TodoWrite for in-session task management when tracker is anything other than `beads`.
- The silent-skip-on-missing-`LINEAR_API_KEY` behavior is preserved.

## [2.37.2] - 2026-02-26

### Added

- **`scripts/workflow-repo-preflight.py`** — Deterministic repo/work-start preflight for `/workflows:work` that emits JSON with current/default branch, dirty state, optional PR metadata, Linear availability, and a recommended next action/prompt.

### Changed

- **`/workflows:work` command** — Phase 1 setup now calls the preflight script and follows structured `recommendation.action` output instead of re-deriving branch/default-branch state from inline shell snippets.

---

## [2.37.1] - 2026-02-25

### Fixed

- Fix AskUserQuestion constraint violation in `/workflows:plan` (7 options → 4+3 sequential) and `/deepen-plan` (5 → 4)

---

## [2.37.0] - 2026-02-25

### Added

- **`integration-boundary-reviewer` agent** — New always-on review agent that identifies untested integration boundaries where application code calls external libraries, APIs, or services. Flags cases where tests validate shapes but not behavior (e.g., constructor arguments that the library doesn't accept, transport type mismatches, tests that fail at auth before reaching integration code). Runs automatically during `/workflows:review`.
- **`test-strategy-reviewer` skill** — Analyze test files for coverage gaps, mock depth issues, and untested integration boundaries. Reports which functions have no tests, which tests mock at the wrong level, and which external library calls are never exercised with real objects.

### Changed

- **`pr-comment-resolver` agent** — Step 4 (Verify the Resolution) now includes integration verification: verify external API call signatures match the library, confirm changed code paths are actually tested, and write smoke tests for new library usage
- **`/workflows:review` command** — Added `integration-boundary-reviewer` to the always-on agents list (alongside `agent-native-reviewer` and `learnings-researcher`)
- **`/workflows:work` command** — Enhanced System-Wide Test Check with 6th question about external library API correctness. Added "External library smoke tests" guidance to Test Continuously section. Added Integration Boundary Verification step to Phase 3 Quality Check.
- **`/deepen-plan` command** — Added Step 4b (Testing Strategy Research) to spawn dedicated research agents for each external library's testing patterns, constructor signatures, and anti-patterns. Added Testing Strategy section to the enhancement format.
- **`setup` skill** — Comprehensive depth now includes `integration-boundary-reviewer`

---

## [2.36.0] - 2026-02-24

### Added

- **Linear integration** — Bidirectional sync between file-based todos and Linear project management
  - **`linear-sync` skill** — Documents the integration pattern, status/priority mappings, configuration, and workflow integration
  - **`/linear:sync` command** — Full bidirectional sync (push local changes + pull Linear changes)
  - **`/linear:status` command** — Show sync dashboard comparing file state with Linear state
  - **`/linear:import` command** — Import a specific Linear issue as a local todo file
  - **`/linear:pull` command** — Pull Linear changes (state, priority, comments, new issues) into files
  - **CLI subcommand `agentic-plugin linear`** — 8 subcommands: sync, push, pull, status, import, create, cancel, config
  - **Graceful degradation** — All Linear operations silently skip when `LINEAR_API_KEY` is not set
  - **Last-write-wins conflict resolution** — Compares Linear `updatedAt` vs file mtime; conflicts logged, never silently dropped
  - **Parent/sub-issue hierarchy** — Plans map to parent Linear issues, spawned todos become sub-issues

### Changed

- **`/workflows:review`** — After creating todo files, pushes them to Linear with optional parent linking
- **`/triage`** — Pulls latest Linear state before presenting items; pushes approved items; cancels skipped items in Linear
- **`/resolve_todo_parallel`** — Pulls latest Linear state before planning; pushes completed state after resolution
- **`/workflows:plan`** — Issue creation now uses `agentic-plugin linear create` instead of `linear issue create`
- **`/workflows:work`** — Syncs with Linear at start and pushes final state on completion
- **`file-todos` skill** — Added `linear_id` and `linear_synced_at` frontmatter documentation
- **`file-todos` todo template** — Added `linear_id` field to YAML frontmatter

---

## [2.35.2] - 2026-02-20

### Changed

- **`/workflows:plan` brainstorm integration** — When plan finds a brainstorm document, it now heavily references it throughout. Added `origin:` frontmatter field to plan templates, brainstorm cross-check in final review, and "Sources" section at the bottom of all three plan templates (MINIMAL, MORE, A LOT). Brainstorm decisions are carried forward with explicit references (`see brainstorm: <path>`) and a mandatory scan before finalizing ensures nothing is dropped.

---

## [2.35.1] - 2026-02-18

### Changed

- **`/workflows:work` system-wide test check** — Added "System-Wide Test Check" to the task execution loop. Before marking a task done, forces five questions: what callbacks/middleware fire when this runs? Do tests exercise the real chain or just mocked isolation? Can failure leave orphaned state? What other interfaces need the same change? Do error strategies align across layers? Includes skip criteria for leaf-node changes. Also added integration test guidance to the "Test Continuously" section.
- **`/workflows:plan` system-wide impact templates** — Added "System-Wide Impact" section to MORE and A LOT plan templates (interaction graph, error propagation, state lifecycle, API surface parity, integration test scenarios) as lightweight prompts to flag risks during planning.

---

## [2.35.0] - 2026-02-17

### Fixed

- **`/lfg` and `/slfg` first-run failures** — Made ralph-loop step optional with graceful fallback when `ralph-wiggum` skill is not installed (#154). Added explicit "do not stop" instruction across all steps (#134).
- **`/workflows:plan` not writing file in pipeline** — Added mandatory "Write Plan File" step with explicit Write tool instructions before Post-Generation Options. The file is now always written to disk before any interactive prompts (#155). Also adds pipeline-mode note to skip AskUserQuestion calls when invoked from LFG/SLFG (#134).
- **Agent namespace typo in `/workflows:plan`** — `Task spec-flow-analyzer(...)` now uses the full qualified name `Task agentic-engineering:workflow:spec-flow-analyzer(...)` to prevent Claude from prepending the wrong `workflows:` prefix (#193).

---

## [2.34.0] - 2026-02-14

### Added

- **Gemini CLI target** — New converter target for [Gemini CLI](https://github.com/google-gemini/gemini-cli). Install with `--to gemini` to convert agents to `.gemini/skills/*/SKILL.md`, commands to `.gemini/commands/*.toml` (TOML format with `description` + `prompt`), and MCP servers to `.gemini/settings.json`. Skills pass through unchanged (identical SKILL.md standard). Namespaced commands create directory structure (`workflows:plan` → `commands/workflows/plan.toml`). 29 new tests. ([#190](https://github.com/EveryInc/compound-engineering-plugin/pull/190))

---

## [2.33.1] - 2026-02-13

### Changed

- **`/workflows:plan` command** - All plan templates now include `status: active` in YAML frontmatter. Plans are created with `status: active` and marked `status: completed` when work finishes.
- **`/workflows:work` command** - Phase 4 now updates plan frontmatter from `status: active` to `status: completed` after shipping. Agents can grep for status to distinguish current vs historical plans.

---

## [2.33.0] - 2026-02-12

### Added

- **`setup` skill** — Interactive configurator for review agents
  - Auto-detects project type (Rails, Python, TypeScript, etc.)
  - Two paths: "Auto-configure" (one click) or "Customize" (pick stack, focus areas, depth)
  - Writes `agentic-engineering.local.md` in project root (tool-agnostic — works for Claude, Codex, OpenCode)
  - Invoked automatically by `/workflows:review` when no settings file exists
- **`learnings-researcher` in `/workflows:review`** — Always-run agent that searches `docs/solutions/` for past issues related to the PR
- **`schema-drift-detector` wired into `/workflows:review`** — Conditional agent for PRs with migrations

### Changed

- **`/workflows:review`** — Now reads review agents from `agentic-engineering.local.md` settings file. Falls back to invoking setup skill if no file exists.
- **`/workflows:work`** — Review agents now configurable via settings file
- **`/release-docs` command** — Moved from plugin to local `.claude/commands/` (repo maintenance, not distributed)

### Removed

- **`/technical_review` command** — Superseded by configurable review agents

---

## [2.32.0] - 2026-02-11

### Added

- **Factory Droid target** — New converter target for [Factory Droid](https://docs.factory.ai). Install with `--to droid` to output agents, commands, and skills to `~/.factory/`. Includes tool name mapping (Claude → Factory), namespace prefix stripping, Task syntax conversion, and agent reference rewriting. 13 new tests (9 converter + 4 writer). ([#174](https://github.com/EveryInc/compound-engineering-plugin/pull/174))

---

## [2.31.1] - 2026-02-09

### Changed

- **`dspy-ruby` skill** — Complete rewrite to DSPy.rb v0.34.3 API: `.call()` / `result.field` patterns, `T::Enum` classes, `DSPy::Tools::Base` / `Toolset`. Added events system, lifecycle callbacks, fiber-local LM context, GEPA optimization, evaluation framework, typed context pattern, BAML/TOON schema formats, storage system, score reporting, RubyLLM adapter. 5 reference files (2 new: toolsets, observability), 3 asset templates rewritten.

## [2.31.0] - 2026-02-08

### Added

- **`document-review` skill** — Brainstorm and plan refinement through structured review ([@Trevin Chow](https://github.com/trevin))
- **`/sync` command** — Sync Claude Code personal config across machines ([@Terry Li](https://github.com/terryli))

### Changed

- **Context token optimization (79% reduction)** — Plugin was consuming 316% of the context description budget, causing Claude Code to silently exclude components. Now at 65% with room to grow:
  - All 29 agent descriptions trimmed from ~1,400 to ~180 chars avg (examples moved to agent body)
  - 18 manual commands marked `disable-model-invocation: true` (side-effect commands like `/lfg`, `/deploy-docs`, `/triage`, etc.)
  - 6 manual skills marked `disable-model-invocation: true` (`orchestrating-swarms`, `git-worktree`, `skill-creator`, `compound-docs`, `file-todos`, `resolve-pr-parallel`)
- **git-worktree**: Remove confirmation prompt for worktree creation ([@Sam Xie](https://github.com/samxie))
- **Prevent subagents from writing intermediary files** in compound workflow ([@Trevin Chow](https://github.com/trevin))

### Fixed

- Fix crash when hook entries have no matcher ([@Roberto Mello](https://github.com/robertomello))
- Fix git-worktree detection where `.git` is a file, not a directory ([@David Alley](https://github.com/davidalley))
- Backup existing config files before overwriting in sync ([@Zac Williams](https://github.com/zacwilliams))
- Note new repository URL ([@Aarni Koskela](https://github.com/aarnikoskela))
- Plugin component counts corrected: 29 agents, 24 commands, 18 skills

---

## [2.30.0] - 2026-02-05

### Added

- **`orchestrating-swarms` skill** - Comprehensive guide to multi-agent orchestration
  - Covers primitives: Agent, Team, Teammate, Leader, Task, Inbox, Message, Backend
  - Documents two spawning methods: subagents vs teammates
  - Explains all 13 TeammateTool operations
  - Includes orchestration patterns: Parallel Specialists, Pipeline, Self-Organizing Swarm
  - Details spawn backends: in-process, tmux, iterm2
  - Provides complete workflow examples
- **`/slfg` command** - Swarm-enabled variant of `/lfg` that uses swarm mode for parallel execution

### Changed

- **`/workflows:work` command** - Added optional Swarm Mode section for parallel execution with coordinated agents

---

## [2.29.0] - 2026-02-04

### Added

- **`schema-drift-detector` agent** - Detects unrelated schema.rb changes in PRs
  - Compares schema.rb diff against migrations in the PR
  - Catches columns, indexes, and tables from other branches
  - Prevents accidental inclusion of local database state
  - Provides clear fix instructions (checkout + migrate)
  - Essential pre-merge check for any PR with database changes

---

## [2.28.0] - 2026-01-21

### Added

- **`/workflows:brainstorm` command** - Guided ideation flow to expand options quickly (#101)

### Changed

- **`/workflows:plan` command** - Smarter research decision logic before deep dives (#100)
- **Research checks** - Mandatory API deprecation validation in research flows (#102)
- **Docs** - Call out experimental OpenCode/Codex providers and install defaults
- **CLI defaults** - `install` pulls from GitHub by default and writes OpenCode/Codex output to global locations

### Merged PRs

- [#102](https://github.com/EveryInc/compound-engineering-plugin/pull/102) feat(research): add mandatory API deprecation validation
- [#101](https://github.com/EveryInc/compound-engineering-plugin/pull/101) feat: Add /workflows:brainstorm command and skill
- [#100](https://github.com/EveryInc/compound-engineering-plugin/pull/100) feat(workflows:plan): Add smart research decision logic

### Contributors

Huge thanks to the community contributors who made this release possible! 🙌

- **[@tmchow](https://github.com/tmchow)** - Brainstorm workflow, research decision logic (2 PRs)
- **[@jaredmorgenstern](https://github.com/jaredmorgenstern)** - API deprecation validation

---

## [2.27.0] - 2026-01-20

### Added

- **`/workflows:plan` command** - Interactive Q&A refinement phase (#88)
  - After generating initial plan, now offers to refine with targeted questions
  - Asks up to 5 questions about ambiguous requirements, edge cases, or technical decisions
  - Incorporates answers to strengthen the plan before finalization

### Changed

- **`/workflows:work` command** - Incremental commits and branch safety (#93)
  - Now commits after each completed task instead of batching at end
  - Added branch protection checks before starting work
  - Better progress tracking with per-task commits

### Fixed

- **`dhh-rails-style` skill** - Fixed broken markdown table formatting (#96)
- **Documentation** - Updated hardcoded year references from 2025 to 2026 (#86, #91)

### Contributors

Huge thanks to the community contributors who made this release possible! 🙌

- **[@tmchow](https://github.com/tmchow)** - Interactive Q&A for plans, incremental commits, year updates (3 PRs!)
- **[@ashwin47](https://github.com/ashwin47)** - Markdown table fix
- **[@rbouschery](https://github.com/rbouschery)** - Documentation year update

### Summary

- 27 agents, 23 commands, 14 skills, 1 MCP server

---

## [2.26.5] - 2026-01-18

### Changed

- **`/workflows:work` command** - Now marks off checkboxes in plan document as tasks complete
  - Added step to update original plan file (`[ ]` → `[x]`) after each task
  - Ensures no checkboxes are left unchecked when work is done
  - Keeps plan as living document showing progress

---

## [2.26.4] - 2026-01-15

### Changed

- **`/workflows:work` command** - PRs now include Compound Engineered badge
  - Updated PR template to include badge at bottom linking to plugin repo
  - Added badge requirement to quality checklist
  - Badge provides attribution and link to the plugin that created the PR

---

## [2.26.3] - 2026-01-14

### Changed

- **`design-iterator` agent** - Now auto-loads design skills at start of iterations
  - Added "Step 0: Discover and Load Design Skills (MANDATORY)" section
  - Discovers skills from ~/.claude/skills/, .claude/skills/, and plugin cache
  - Maps user context to relevant skills (Swiss design → swiss-design skill, etc.)
  - Reads SKILL.md files to load principles into context before iterating
  - Extracts key principles: grid specs, typography rules, color philosophy, layout principles
  - Skills are applied throughout ALL iterations for consistent design language

---

## [2.26.2] - 2026-01-14

### Changed

- **`/test-browser` command** - Clarified to use agent-browser CLI exclusively
  - Added explicit "CRITICAL: Use agent-browser CLI Only" section
  - Added warning: "DO NOT use Chrome MCP tools (mcp__claude-in-chrome__*)"
  - Added Step 0: Verify agent-browser installation before testing
  - Added full CLI reference section at bottom
  - Added Next.js route mapping patterns

---

## [2.26.1] - 2026-01-14

### Changed

- **`best-practices-researcher` agent** - Now checks skills before going online
  - Phase 1: Discovers and reads relevant SKILL.md files from plugin, global, and project directories
  - Phase 2: Only goes online for additional best practices if skills don't provide enough coverage
  - Phase 3: Synthesizes all findings with clear source attribution (skill-based > official docs > community)
  - Skill mappings: Rails → dhh-rails-style, Frontend → frontend-design, AI → agent-native-architecture, etc.
  - Prioritizes curated skill knowledge over external sources for trivial/common patterns

---

## [2.26.0] - 2026-01-14

### Added

- **`/lfg` command** - Full autonomous engineering workflow
  - Orchestrates complete feature development from plan to PR
  - Runs: plan → deepen-plan → work → review → resolve todos → test-browser → feature-video
  - Uses ralph-loop for autonomous completion
  - Migrated from local command, updated to use `/test-browser` instead of `/playwright-test`

### Summary

- 27 agents, 21 commands, 14 skills, 1 MCP server

---

## [2.25.0] - 2026-01-14

### Added

- **`agent-browser` skill** - Browser automation using Vercel's agent-browser CLI
  - Navigate, click, fill forms, take screenshots
  - Uses ref-based element selection (simpler than Playwright)
  - Works in headed or headless mode

### Changed

- **Replaced Playwright MCP with agent-browser** - Simpler browser automation across all browser-related features:
  - `/test-browser` command - Now uses agent-browser CLI with headed/headless mode option
  - `/feature-video` command - Uses agent-browser for screenshots
  - `design-iterator` agent - Browser automation via agent-browser
  - `design-implementation-reviewer` agent - Screenshot comparison
  - `figma-design-sync` agent - Design verification
  - `bug-reproduction-validator` agent - Bug reproduction
  - `/review` workflow - Screenshot capabilities
  - `/work` workflow - Browser testing

- **`/test-browser` command** - Added "Step 0" to ask user if they want headed (visible) or headless browser mode

### Removed

- **Playwright MCP server** - Replaced by agent-browser CLI (simpler, no MCP overhead)
- **`/playwright-test` command** - Renamed to `/test-browser`

### Summary

- 27 agents, 20 commands, 14 skills, 1 MCP server

---

## [2.23.2] - 2026-01-09

### Changed

- **`/reproduce-bug` command** - Enhanced with Playwright visual reproduction:
  - Added Phase 2 for visual bug reproduction using browser automation
  - Step-by-step guide for navigating to affected areas
  - Screenshot capture at each reproduction step
  - Console error checking
  - User flow reproduction with clicks, typing, and snapshots
  - Better documentation structure with 4 clear phases

### Summary

- 27 agents, 21 commands, 13 skills, 2 MCP servers

---

## [2.23.1] - 2026-01-08

### Changed

- **Agent model inheritance** - All 26 agents now use `model: inherit` so they match the user's configured model. Only `lint` keeps `model: haiku` for cost efficiency. (fixes #69)

### Summary

- 27 agents, 21 commands, 13 skills, 2 MCP servers

---

## [2.23.0] - 2026-01-08

### Added

- **`/agent-native-audit` command** - Comprehensive agent-native architecture review
  - Launches 8 parallel sub-agents, one per core principle
  - Principles: Action Parity, Tools as Primitives, Context Injection, Shared Workspace, CRUD Completeness, UI Integration, Capability Discovery, Prompt-Native Features
  - Each agent produces specific score (X/Y format with percentage)
  - Generates summary report with overall score and top 10 recommendations
  - Supports single principle audit via argument

### Summary

- 27 agents, 21 commands, 13 skills, 2 MCP servers

---

## [2.22.0] - 2026-01-05

### Added

- **`rclone` skill** - Upload files to S3, Cloudflare R2, Backblaze B2, and other cloud storage providers

### Changed

- **`/feature-video` command** - Enhanced with:
  - Better ffmpeg commands for video/GIF creation (proper scaling, framerate control)
  - rclone integration for cloud uploads
  - Screenshot copying to project folder
  - Improved upload options workflow

### Summary

- 27 agents, 20 commands, 13 skills, 2 MCP servers

---

## [2.21.0] - 2026-01-05

### Fixed

- Version history cleanup after merge conflict resolution

### Summary

This release consolidates all recent work:
- `/feature-video` command for recording PR demos
- `/deepen-plan` command for enhanced planning
- `create-agent-skills` skill rewrite (official spec compliance)
- `agent-native-architecture` skill major expansion
- `dhh-rails-style` skill consolidation (merged dhh-ruby-style)
- 27 agents, 20 commands, 12 skills, 2 MCP servers

---

## [2.20.0] - 2026-01-05

### Added

- **`/feature-video` command** - Record video walkthroughs of features using Playwright

### Changed

- **`create-agent-skills` skill** - Complete rewrite to match Anthropic's official skill specification

### Removed

- **`dhh-ruby-style` skill** - Merged into `dhh-rails-style` skill

---

## [2.19.0] - 2025-12-31

### Added

- **`/deepen-plan` command** - Power enhancement for plans. Takes an existing plan and runs parallel research sub-agents for each major section to add:
  - Best practices and industry patterns
  - Performance optimizations
  - UI/UX improvements (if applicable)
  - Quality enhancements and edge cases
  - Real-world implementation examples

  The result is a deeply grounded, production-ready plan with concrete implementation details.

### Changed

- **`/workflows:plan` command** - Added `/deepen-plan` as option 2 in post-generation menu. Added note: if running with ultrathink enabled, automatically run deepen-plan for maximum depth.

## [2.18.0] - 2025-12-25

### Added

- **`agent-native-architecture` skill** - Added **Dynamic Capability Discovery** pattern and **Architecture Review Checklist**:

  **New Patterns in mcp-tool-design.md:**
  - **Dynamic Capability Discovery** - For external APIs (HealthKit, HomeKit, GraphQL), build a discovery tool (`list_*`) that returns available capabilities at runtime, plus a generic access tool that takes strings (not enums). The API validates, not your code. This means agents can use new API capabilities without code changes.
  - **CRUD Completeness** - Every entity the agent can create must also be readable, updatable, and deletable. Incomplete CRUD = broken action parity.

  **New in SKILL.md:**
  - **Architecture Review Checklist** - Pushes reviewer findings earlier into the design phase. Covers tool design (dynamic vs static, CRUD completeness), action parity (capability map, edit/delete), UI integration (agent → UI communication), and context injection.
  - **Option 11: API Integration** - New intake option for connecting to external APIs like HealthKit, HomeKit, GraphQL
  - **New anti-patterns:** Static Tool Mapping (building individual tools for each API endpoint), Incomplete CRUD (create-only tools)
  - **Tool Design Criteria** section added to success criteria checklist

  **New in shared-workspace-architecture.md:**
  - **iCloud File Storage for Multi-Device Sync** - Use iCloud Documents for your shared workspace to get free, automatic multi-device sync without building a sync layer. Includes implementation pattern, conflict handling, entitlements, and when NOT to use it.

### Philosophy

This update codifies a key insight for **agent-native apps**: when integrating with external APIs where the agent should have the same access as the user, use **Dynamic Capability Discovery** instead of static tool mapping. Instead of building `read_steps`, `read_heart_rate`, `read_sleep`... build `list_health_types` + `read_health_data(dataType: string)`. The agent discovers what's available, the API validates the type.

Note: This pattern is specifically for agent-native apps following the "whatever the user can do, the agent can do" philosophy. For constrained agents with intentionally limited capabilities, static tool mapping may be appropriate.

---

## [2.17.0] - 2025-12-25

### Enhanced

- **`agent-native-architecture` skill** - Major expansion based on real-world learnings from building the Every Reader iOS app. Added 5 new reference documents and expanded existing ones:

  **New References:**
  - **dynamic-context-injection.md** - How to inject runtime app state into agent system prompts. Covers context injection patterns, what context to inject (resources, activity, capabilities, vocabulary), implementation patterns for Swift/iOS and TypeScript, and context freshness.
  - **action-parity-discipline.md** - Workflow for ensuring agents can do everything users can do. Includes capability mapping templates, parity audit process, PR checklists, tool design for parity, and context parity guidelines.
  - **shared-workspace-architecture.md** - Patterns for agents and users working in the same data space. Covers directory structure, file tools, UI integration (file watching, shared stores), agent-user collaboration patterns, and security considerations.
  - **agent-native-testing.md** - Testing patterns for agent-native apps. Includes "Can Agent Do It?" tests, the Surprise Test, automated parity testing, integration testing, and CI/CD integration.
  - **mobile-patterns.md** - Mobile-specific patterns for iOS/Android. Covers background execution (checkpoint/resume), permission handling, cost-aware design (model tiers, token budgets, network awareness), offline handling, and battery awareness.

  **Updated References:**
  - **architecture-patterns.md** - Added 3 new patterns: Unified Agent Architecture (one orchestrator, many agent types), Agent-to-UI Communication (shared data store, file watching, event bus), and Model Tier Selection (fast/balanced/powerful).

  **Updated Skill Root:**
  - **SKILL.md** - Expanded intake menu (now 10 options including context injection, action parity, shared workspace, testing, mobile patterns). Added 5 new agent-native anti-patterns (Context Starvation, Orphan Features, Sandbox Isolation, Silent Actions, Capability Hiding). Expanded success criteria with agent-native and mobile-specific checklists.

- **`agent-native-reviewer` agent** - Significantly enhanced with comprehensive review process covering all new patterns. Now checks for action parity, context parity, shared workspace, tool design (primitives vs workflows), dynamic context injection, and mobile-specific concerns. Includes detailed anti-patterns, output format template, quick checks ("Write to Location" test, Surprise test), and mobile-specific verification.

### Philosophy

These updates operationalize a key insight from building agent-native mobile apps: **"The agent should be able to do anything the user can do, through tools that mirror UI capabilities, with full context about the app state."** The failure case that prompted these changes: an agent asked "what reading feed?" when a user said "write something in my reading feed"—because it had no `publish_to_feed` tool and no context about what "feed" meant.

## [2.16.0] - 2025-12-21

### Enhanced

- **`dhh-rails-style` skill** - Massively expanded reference documentation incorporating patterns from Marc Köhlbrugge's Unofficial 37signals Coding Style Guide:
  - **controllers.md** - Added authorization patterns, rate limiting, Sec-Fetch-Site CSRF protection, request context concerns
  - **models.md** - Added validation philosophy, let it crash philosophy (bang methods), default values with lambdas, Rails 7.1+ patterns (normalizes, delegated types, store accessor), concern guidelines with touch chains
  - **frontend.md** - Added Turbo morphing best practices, Turbo frames patterns, 6 new Stimulus controllers (auto-submit, dialog, local-time, etc.), Stimulus best practices, view helpers, caching with personalization, broadcasting patterns
  - **architecture.md** - Added path-based multi-tenancy, database patterns (UUIDs, state as records, hard deletes, counter caches), background job patterns (transaction safety, error handling, batch processing), email patterns, security patterns (XSS, SSRF, CSP), Active Storage patterns
  - **gems.md** - Added expanded what-they-avoid section (service objects, form objects, decorators, CSS preprocessors, React/Vue), testing philosophy with Minitest/fixtures patterns

### Credits

- Reference patterns derived from [Marc Köhlbrugge's Unofficial 37signals Coding Style Guide](https://github.com/marckohlbrugge/unofficial-37signals-coding-style-guide)

## [2.15.2] - 2025-12-21

### Fixed

- **All skills** - Fixed spec compliance issues across 12 skills:
  - Reference files now use proper markdown links (`[file.md](./references/file.md)`) instead of backtick text
  - Descriptions now use third person ("This skill should be used when...") per skill-creator spec
  - Affected skills: agent-native-architecture, andrew-kane-gem-writer, compound-docs, create-agent-skills, dhh-rails-style, dspy-ruby, every-style-editor, file-todos, frontend-design, gemini-imagegen

### Added

- **CLAUDE.md** - Added Skill Compliance Checklist with validation commands for ensuring new skills meet spec requirements

## [2.15.1] - 2025-12-18

### Changed

- **`/workflows:review` command** - Section 7 now detects project type (Web, iOS, or Hybrid) and offers appropriate testing. Web projects get `/playwright-test`, iOS projects get `/xcode-test`, hybrid projects can run both.

## [2.15.0] - 2025-12-18

### Added

- **`/xcode-test` command** - Build and test iOS apps on simulator using XcodeBuildMCP. Automatically detects Xcode project, builds app, launches simulator, and runs test suite. Includes retries for flaky tests.

- **`/playwright-test` command** - Run Playwright browser tests on pages affected by current PR or branch. Detects changed files, maps to affected routes, generates/runs targeted tests, and reports results with screenshots.

## [2.6.0] - 2024-11-26

### Removed

- **`feedback-codifier` agent** — Removed from workflow agents. Agent count reduced from 24 to 23.

## [2.5.0] - 2024-11-25

### Added

- **`/report-bug` command** — New slash command for reporting bugs in the agentic-engineering plugin. Provides a structured workflow that gathers bug information through guided questions, collects environment details automatically, and creates a GitHub issue in the aagnone3/agentic-engineering repository.

## [2.4.1] - 2024-11-24

### Changed

- **`design-iterator` agent** — Added focused screenshot guidance: always capture only the target element/area instead of full page screenshots. Includes `browser_resize` recommendations, element-targeted screenshot workflow using `browser_snapshot` refs, and explicit instruction to never use fullPage mode.

## [2.4.0] - 2024-11-24

### Fixed

- **MCP Configuration** — Moved MCP servers back to `plugin.json` following working examples from anthropics/life-sciences plugins.
- **Context7 URL** — Updated to use HTTP type with correct endpoint URL.

## [2.3.0] - 2024-11-24

### Changed

- **MCP Configuration** — Moved MCP servers from inline `plugin.json` to a separate `.mcp.json` file per Claude Code best practices.

## [2.2.1] - 2024-11-24

### Fixed

- **Playwright MCP Server** — Added missing `"type": "stdio"` field required for MCP server configuration to load properly.

## [2.2.0] - 2024-11-24

### Added

- **Context7 MCP Server** — Bundled Context7 for instant framework documentation lookup. Provides up-to-date docs for Rails, React, Next.js, and more than 100 other frameworks.

## [2.1.0] - 2024-11-24

### Added

- **Playwright MCP Server** — Bundled `@playwright/mcp` for browser automation across all projects. Provides screenshot, navigation, click, fill, and evaluate tools.

### Changed

- **Replaced all Puppeteer references with Playwright** across agents and commands:
  - `bug-reproduction-validator` agent
  - `design-iterator` agent
  - `design-implementation-reviewer` agent
  - `figma-design-sync` agent
  - `generate_command` command

## [2.0.2] - 2024-11-24

### Changed

- **`design-iterator` agent** — Updated description to emphasize proactive usage when design work isn't coming together on first attempt.

## [2.0.1] - 2024-11-24

### Added

- **`CLAUDE.md`** — Project instructions with versioning requirements.
- **`docs/solutions/plugin-versioning-requirements.md`** — Workflow documentation.

## [2.0.0] - 2024-11-24

Major reorganization consolidating agents, commands, and skills from multiple sources into a single, well-organized plugin.

### Added

**New Agents (seven):**
- `design-iterator` - Iteratively refine UI components through systematic design iterations
- `design-implementation-reviewer` - Verify UI implementations match Figma design specifications
- `figma-design-sync` - Synchronize web implementations with Figma designs
- `bug-reproduction-validator` - Systematically reproduce and validate bug reports
- `spec-flow-analyzer` - Analyze user flows and identify gaps in specifications
- `lint` - Run linting and code quality checks on Ruby and ERB files
- `ankane-readme-writer` - Create READMEs following Ankane-style template for Ruby gems

**New Commands (nine):**
- `/changelog` - Create engaging changelogs for recent merges
- `/plan_review` - Multi-agent plan review in parallel
- `/resolve_parallel` - Resolve TODO comments in parallel
- `/resolve_pr_parallel` - Resolve PR comments in parallel
- `/reproduce-bug` - Reproduce bugs using logs and console
- `/prime` - Prime/setup command
- `/create-agent-skill` - Create or edit Claude Code skills
- `/heal-skill` - Fix skill documentation issues
- `/codify` - Document solved problems for knowledge base

**New Skills (10):**
- `andrew-kane-gem-writer` - Write Ruby gems following Andrew Kane's patterns
- `codify-docs` - Capture solved problems as categorized documentation
- `create-agent-skills` - Expert guidance for creating Claude Code skills
- `dhh-ruby-style` - Write Ruby/Rails code in DHH's 37signals style
- `dspy-ruby` - Build type-safe LLM applications with DSPy.rb
- `every-style-editor` - Review copy for Every's style guide compliance
- `file-todos` - File-based todo tracking system
- `frontend-design` - Create production-grade frontend interfaces
- `git-worktree` - Manage Git worktrees for parallel development
- `skill-creator` - Guide for creating effective Claude Code skills

### Changed

**Agents reorganized by category:**
- `review/` (10 agents) - Code quality, security, performance reviewers
- `research/` (four agents) - Documentation, patterns, history analysis
- `design/` (three agents) - UI/design review and iteration
- `workflow/` (six agents) - PR resolution, bug validation, linting
- `docs/` (one agent) - README generation

**Summary:**

| Component | v1.1.0 | v2.0.0 | Change |
| --- | --- | --- | --- |
| Agents | 17 | 24 | +7 |
| Commands | 6 | 15 | +9 |
| Skills | 1 | 11 | +10 |

## [1.1.0] - 2024-11-22

### Added

- **`gemini-imagegen` skill**
  - Text-to-image generation with Google's Gemini API
  - Image editing and manipulation
  - Multi-turn refinement via chat interface
  - Multiple reference image composition (up to 14 images)
  - Model support: `gemini-2.5-flash-image` and `gemini-3-pro-image-preview`

### Fixed

- Corrected component counts in documentation (17 agents, not 15).

## [1.0.0] - 2024-10-09

Initial release of the agentic-engineering plugin.

### Added

**17 Specialized Agents**

**Code Review (five):**
- `kieran-rails-reviewer` - Rails code review with strict conventions
- `kieran-python-reviewer` - Python code review with quality standards
- `kieran-typescript-reviewer` - TypeScript code review
- `dhh-rails-reviewer` - Rails review from DHH's perspective
- `code-simplicity-reviewer` - Final pass for simplicity and minimalism

**Analysis & Architecture (four):**
- `architecture-strategist` - Architectural decisions and compliance
- `pattern-recognition-specialist` - Design pattern analysis
- `security-sentinel` - Security audits and vulnerability assessments
- `performance-oracle` - Performance analysis and optimization

**Research (four):**
- `framework-docs-researcher` - Framework documentation research
- `best-practices-researcher` - External best practices gathering
- `git-history-analyzer` - Git history and code evolution analysis
- `repo-research-analyst` - Repository structure and conventions

**Workflow (three):**
- `every-style-editor` - Every's style guide compliance
- `pr-comment-resolver` - PR comment resolution
- `feedback-codifier` - Feedback pattern codification

**Six Slash Commands:**
- `/plan` - Create implementation plans
- `/review` - Comprehensive code reviews
- `/work` - Execute work items systematically
- `/triage` - Triage and prioritize issues
- `/resolve_todo_parallel` - Resolve TODOs in parallel
- `/generate_command` - Generate new slash commands

**Infrastructure:**
- MIT license
- Plugin manifest (`plugin.json`)
- Pre-configured permissions for Rails development
