# Changelog

All notable changes to the agentic-engineering plugin will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased] — 3.0.0

### Removed

- **BREAKING: Linear support removed entirely** (part 1 of the unified-lifecycle work, issue #39). Deleted the four `/linear:*` commands (`sync`, `status`, `import`, `pull`), the `linear-sync` skill, and the `agentic-plugin linear` CLI (~1,650 lines of TypeScript: `src/commands/linear.ts`, `src/sync/linear.ts`, `src/sync/linear-api.ts`, `src/types/linear.ts`). The issue-tracker resolution chain is now `beads | github | none` — `LINEAR_API_KEY` is no longer consulted, the `issue_tracker_ambiguous` / `linear_api_key_present` preflight fields are gone, and `linear_issue:` is no longer accepted by the plan-tracker-guard Stop hook (use `bead_id:` or `github_issue:`). Todo-file frontmatter drops `linear_id` / `linear_synced_at`. Every workflow command's Linear dispatch branch (work, plan, review, triage, resolve_todo_parallel, land-pr, setup, file-todos, merge) was removed rather than deprecated: unused dispatch branches are untested surface where faithfulness dies silently. Migration: existing plans with `linear_issue:` frontmatter should add a `github_issue:` (or `bead_id:`) on next touch; git history is the archive if Linear support is ever needed as a companion plugin. Counts: 31→27 commands, 23→22 skills.

### Changed

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
