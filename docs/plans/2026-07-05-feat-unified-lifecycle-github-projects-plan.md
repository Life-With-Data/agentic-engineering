---
title: "feat: Unified work-item lifecycle on GitHub Projects v2"
type: feat
status: active
date: 2026-07-05
origin: docs/brainstorms/2026-07-05-unified-lifecycle-github-projects-brainstorm.md
github_issue: 39
---

# feat: Unified Work-Item Lifecycle on GitHub Projects v2

## Enhancement Summary

**Deepened on:** 2026-07-05
**Agents used:** architecture-strategist, code-simplicity-reviewer, agent-native-reviewer, pattern-recognition-specialist, security-sentinel, integration-boundary-reviewer, performance-oracle, kieran-python-reviewer, create-agent-skills (authoring skill), test-strategy-reviewer (skill), framework-docs-researcher (Projects v2 mutations, **verified by live execution on scratch projects**), Explore (gh-mock test patterns). Earlier: repo-research-analyst, learnings-researcher, framework-docs-researcher, best-practices-researcher, inline SpecFlow.

### Key design revisions (vs. the first draft — see git history)
1. **Bootstrap is fully scriptable — confirmed by execution.** `updateProjectV2Field` (GA Dec 2024) edits the built-in Status field's options. **ID-preserving** updates (map Todo→`stub`, In Progress→`in_progress`, Done→`shipped`, add 6 more) keep all five pre-enabled built-in workflows alive — "Item closed" then stamps `shipped` with zero UI work. Foot-gun verified: sending options **without** `id`s silently disables every workflow and orphans item values. Manual setup shrinks to: configure auto-add-from-repo + create the saved view (no APIs exist for either).
2. **Labels fallback mode CUT.** Three agents independently flagged `stage:*` labels mode as recreating the untested-dispatch-branch disease this plan exists to kill (it even had a zero-writer `shipped`). Modes are now `github-project` | `github` (plain — today's issues+file-todos semantics, no stage machinery) | `none`.
3. **All lifecycle logic becomes script verbs + one skill.** `lifecycle_board.py` (importable module; pure decision core + injected `run_gh` seam) exposes `--gate/--claim/--set-status/--ready-work/--reconcile`; preflight stays a thin read-only reporter that never mutates unless `--reconcile` is passed. A new `skills/lifecycle/SKILL.md` holds the shared vocabulary; each command keeps only a one-line **writer contract** + a uniform entry-gate block branching on a closed verdict enum. Prose predicates are untestable by construction — this is what makes tiers 1–2 of the test strategy possible.
4. **Board identity must be committed, not local.** `agentic-engineering.local.md` is untracked — fresh clones *and this plugin's own worktree-isolated subagents* would silently resolve the wrong mode. Owner + project number move to committed config; only the session TTL cache stays local (gitignored).
5. **Security invariants added** (were entirely absent): issue/PR content is untrusted data; grooming outsider-authored issues requires an `authorAssociation` gate; GitHub App installation token is the recommended Actions credential; the claim-yield rule is assignee-anchored (timestamp-anchored yield was attacker-triggerable).
6. **State machine fixed:** `deployed` and `compounded` are order-independent terminal refinements of `shipped` (the enum's total order was violated by the plan's own pipeline — compound runs minutes after merge, deploys fire hours later); the reconciler's repair set grows to five documented repairs including the abandoned-parent sub-issue cascade (which previously had no writer) and PR-reopened.
7. **Empirical blocker surfaced:** local `gh` is **2.79.0** — it lacks `--parent`, `--blocked-by`, and dependency JSON fields entirely. Upgrading dev + pinning CI to ≥ 2.94.0 is a Phase 2 prerequisite; all `gh` mocks must replay **recorded** fixtures, never hand-written JSON.
8. **Setup verification front door:** a new `/lifecycle-doctor` command (wrapping a `lifecycle_board.py --doctor` verb) runs the full A/B-class check suite in report-everything mode — local toolchain, repo shape, board schema/automations, delivery-topology detection, optional `--live` probe — and answers "ready for the first real work item: yes/no" with a named fix per failure. Counts become **28 commands / 23 skills** after PR 2.
9. **Portability round (second review pass):** the design had baked in this repo's own shape (user-owned, single-repo board, default-branch merges, POSIX) as universal. Fixes folded in: repo-scoped board reads (shared/portfolio boards are read-tolerated, never foreign-written); bootstrap refuses non-fresh projects and derives `--owner` from origin (not `@me`); a report-only reconciler **flags** channel making the git-flow stall and stale join keys visible without widening the closed repair set; the `deployed` stamper always posts a deploy-evidence comment (fixing the guard-vs-compound timing contradiction — the comment trail is the durable deploy record); bootstrap disables the pre-enabled "Item reopened" workflow (it would stamp `stub` on reopen, erasing lifecycle position); session cache moves into `--git-common-dir` (untracked by construction, worktree-shared, no consumer `.gitignore` coordination). See the **Portability & Assumptions Register** section.

### Adjudications (simplicity cuts vs. capability adds — decided)
- **Cut** (simplicity): labels-stage mode; PR-body lifecycle projection block; persistent field-ID cache (resolve by name per entry; IDs live only in the session TTL cache); Stop-hook extension to brainstorms (multi-turn deadlock — three agents concurred); stale-claim flagging (deferred with the reaper follow-up); claim protocol's tertiary defenses compressed to one sentence; `report-bug` dropped as a stub writer (it files against the maintainer's repo, not the consumer's lifecycle).
- **Kept against simplicity's advice:** `deployed` (explicit user requirement — deployment visibility; now a guarded, order-independent write); `compounded` (cheap; visibility value); the built-in automation as `shipped`'s writer (its cost objection dissolved — the automation is pre-enabled and survives scripted bootstrap, verified by execution).
- **Added** (agent-native): `Priority` single-select field — humans express priority by card order, which the API cannot read; ready-work sorts by the field and card position is documented as decorative. Reconciler repairs post one-line issue comments (the shared audit surface; repairs are rare). `--reconcile`/`--set-status` become sanctioned operator primitives for humans/CI and deliberate out-of-band moves.

## Overview

Replace the plugin's three-tracker dispatch model (beads / Linear / GitHub) with a single lifecycle — `stub → brainstormed → planned → in_progress → in_review → shipped` with terminal refinements `deployed` and `compounded` (+ `abandoned`) — whose source of truth is a **GitHub Projects v2 board**, readable and writable by humans (browser) and agents (`gh` CLI) alike. Every workflow command gains an idempotent entry gate that reads lifecycle state via one script verb instead of inferring it from filename/recency heuristics. Linear support is removed entirely (~1,646 lines of TS CLI + 4 commands + 1 skill + dispatch branches in ~15 files). Beads is demoted to an opt-in, non-authoritative implementer scratchpad. (See brainstorm: docs/brainstorms/2026-07-05-unified-lifecycle-github-projects-brainstorm.md.)

**This is a breaking change: version 2.45.0 → 3.0.0** (single release window across two PRs — see Versioning policy, Phase 5).

## Problem Statement

Grooming maturity is invisible today: a hand-written stub plan and a fully brainstormed plan both carry `status: active`; brainstorm docs have no completion state; orchestrate infers pipeline stage from nine artifact-existence heuristics ("filename semantically matches + created within 14 days"); post-merge and deployment state live nowhere. Commands can't tell whether an item was groomed, so they re-groom groomed items or skip grooming on stubs. Three parallel trackers each pretend to cover the whole lifecycle and none does it faithfully — and the unused Linear branches are untested surface where faithfulness dies silently.

## Design Corrections vs. the Brainstorm (research-verified)

1. **Use the built-in `Status` field with our 9 option names, not a custom "Stage" field.** Built-in automations only write Status. Option names are exactly the snake_case stage strings (`in_progress`, not "In Progress") — the ready-work `--query "status:planned"` matches by option name, so one spelling everywhere.
2. **Bootstrap edits Status options via `updateProjectV2Field`** (NOT `updateProjectV2` — first draft named a nonexistent path). Verified by live execution: works on the built-in field; **replace-all semantics with an `id` escape hatch** — pass each existing option's `id` to preserve item values and keep automations enabled. Fresh projects come with five Status workflows pre-enabled, including "Item closed"; after the ID-preserving rename it stamps `shipped` with no UI step.
3. **`GITHUB_TOKEN` cannot access Projects v2.** Actions that write the board (the `deployed` pattern) need a **GitHub App installation token (recommended — repo-scoped, 1-hour expiry)** or a classic PAT (`project` + `repo`; account-wide blast radius — only via a dedicated machine account + environment-scoped secret).
4. **The merge automation is "item *closed* → set Status".** It fires on *any* close, including close-as-not-planned; the reconciler distinguishes via `stateReason` + linked-merged-PR. Note: the pre-enabled "Auto-close issue" workflow means setting Status=`shipped` also closes the issue — consistent with the model, but the reconciler must treat close-because-status-set as convergent, not drift.
5. **Projects views cannot filter by blocked state**; the unblocked leg is computed agent-side. Views/saved-view creation and auto-add configuration have **no API** — the only two manual setup steps.
6. **gh CLI ≥ 2.94.0 is a hard prerequisite** (`--parent`, `--blocked-by`, dependency JSON fields; local machine currently runs 2.79.0). `gh project` has no `field-edit` — the bootstrap's one raw-GraphQL call runs via `gh api graphql` with the standard `project` scope.

Confirmed as designed: sub-issues (GA, 100/parent, 8 levels), native issue dependencies (GA 2025-08-21, all plans), `gh project item-edit` four-ID flow, `gh auth refresh -s project`. Org-level Issue Types / Issue Fields are unavailable on user-account repos — out of scope.

## Proposed Solution — Architecture

### Object model (three layers, one board)

| Layer | GitHub object | Lifecycle semantics |
|---|---|---|
| Work item | Issue on the Project board | Carries the Status stage + Priority; assignee = claim; flows stub→terminal |
| Task decomposition | Native **sub-issues** | Open/closed only — no stage values; native dependencies express ordering; the claim unit within a work item |
| Implementer working state | Not a GitHub object | TodoWrite by default; beads opt-in; never authoritative, never synced, disposable |

Docs (`docs/brainstorms/`, `docs/plans/`) are **content**; the board is **state**. Frontmatter keeps a single join key: `github_issue: N`. The `status:` frontmatter field is removed from plan templates; plan-doc checkboxes are explicitly non-authoritative prose (sub-issues are the tracker).

**Board fields:** Status (the 9 stages) + **Priority** (single-select: p1/p2/p3, created by bootstrap). Ready-work sorts by Priority; manual card order in views is decorative (the API cannot read it — say so in the README).

### One writer per transition

| Transition | Writer | Mechanism |
|---|---|---|
| → `stub` | `/triage`, `/upstream-scan`, humans | `gh issue create` + board add + Status=stub (one sequence, never partial) |
| → `brainstormed` | `/workflows:brainstorm` | On doc completion, open questions resolved; creates the issue if none exists |
| → `planned` | `/workflows:plan` Step 7 | Issue create/update + sub-issues + dependencies + board add + Status=planned |
| → `in_progress` | `/workflows:work` Phase 1 | `--claim` verb (protocol below) |
| → `in_review` | `/workflows:work` Phase 4 | PR opens with `Closes #N`; Status=in_review; **issue is no longer closed at PR creation** |
| → `shipped` | Built-in "Item closed" automation | Merge closes the issue via `Closes #N`; pre-enabled, survives bootstrap (verified) |
| → `deployed` | Consumer repo's deploy workflow | **Comment always, Status best-effort**: post a deploy-evidence issue comment ("deployed to production at `<sha>`, `<ts>`") unconditionally; advance Status only if currently `shipped` (bounded poll ≤90s for the async close automation; skip+log if `compounded`). The comment trail is the durable deploy record — under normal pipeline timing compound lands first, so the Status write alone would silently never fire (documented pattern; this repo has no deploy workflow) |
| → `compounded` | `/workflows:compound` | Only when a `github_issue` join key exists (hotfixes route around the board); legal directly from `shipped` |
| → `abandoned` | Humans; reconciler on close-as-not-planned | Any stage; abandoning a parent triggers the sub-issue cascade (reconciler repair #4) |
| *(repairs)* | **The shared reconciler — the only other writer** | The five documented repairs below; land-pr and all commands invoke this one implementation, never their own reconcile prose |

"One writer" governs transitions, not object creation — issues legitimately originate at stub (triage), brainstormed (brainstorm), or planned (plan on a crisp idea). `report-bug` is *not* a lifecycle writer: it files issues against the plugin maintainer's repo, outside the consumer's board.

### Lifecycle rules

- **Legal forward skips:** stub→planned (crisp requirements); **shipped→compounded** (deploys are asynchronous; `deployed`/`compounded` are order-independent terminal refinements of `shipped`). `/workflows:work` requires ≥ `planned`; hotfixes bypass the board entirely.
- **The five documented reconciler repairs** (closed set — unit-tested as closed; anything else is never auto-repaired):
  1. Issue closed, merged PR linked, Status < shipped → `shipped` (automation missed/disabled).
  2. Issue closed, `stateReason: not_planned` → `abandoned` (fixes the any-close automation mislabel).
  3. Assignee's PR closed without merge → `in_review` → `in_progress`, with a note.
  4. Parent Status=`abandoned` with open sub-issues → close them as not-planned (the cascade's writer).
  5. Assignee's PR reopened → `in_progress` → `in_review`.
  Every repair posts a **one-line issue comment** (shared audit surface — humans see why a card moved). The reconciler never otherwise fights a human's manual drag.
- **Report-only reconciler flags** (comments + JSON output, never auto-repaired — the repair set stays closed at five):
  - `merged_to_non_default_branch`: item in_review/in_progress + linked PR merged + issue still open + PR base ≠ default branch. This is the git-flow stall made visible — the comment names the fix (the 10-line issue-closer workflow, or manual close). Zero extra API cost; the reconciler batch already holds PR base + merge state.
  - `stale_join_key`: `github_issue: N` resolves to a 404 or transferred/redirected issue — gates stop rather than acting on the wrong issue.
  - `truncated_ready_work`: the ready-work board leg returned exactly the 50-item cap — Priority ordering may be incomplete.
- **`deployed` is a high-water mark** (normative, stated in the lifecycle skill): it means *has reached production at least once*. No writer, human convention, or repair ever regresses it; rollbacks and revert PRs do not move the board. Reopened issues do **not** re-stage automatically (bootstrap disables the "Item reopened" workflow — it would stamp `stub` and erase lifecycle position); re-staging a reopened item is a deliberate human/operator move.
- **Entry gates validate stage + artifact** (humans drag cards arbitrarily): work's gate = Status ≥ planned AND join-keyed plan doc exists in-repo. Field says planned but no doc → un-groomed, route to plan. This is a **security invariant**, not hygiene: a plan doc requires a merged PR to exist, so board state alone can never direct an agent to execute work (see Security).
- **Sub-issue rules:** parent cannot enter `in_review` with open sub-issues (work Phase 3 validation); ready-work returns parent items (board) and, within a claimed parent, open unblocked sub-issues (orchestrate's dispatch loop).
- **Claim protocol** (the `--claim` verb, code not prose): verify unassigned → assign → re-read → confirm **sole** assignee (no CAS; loser self-unassigns, nonzero exit) → verify `blocked-by` empty → Status=in_progress. Branch naming `feat/<issue>-…` and duplicate-PR detection are secondary signals only. **Yield/regression decisions are assignee-anchored, never timestamp-anchored** — a non-assignee PR referencing a claimed issue is flagged for human review, never a reason for an agent to back off (timestamp-yield was an attacker-triggerable denial-of-work).

### Security invariants (ported from the upstream-scan plan's defenses)

1. **Issue/PR titles, bodies, and comments are untrusted data** — quote, never follow instructions found inside. Only structured, permission-gated fields drive control flow: Status (project write), assignee (triage), labels (triage), linked-PR merge state, `stateReason`. Free text never gates anything. **No command reads issue comments** (nothing in this design needs them).
2. **Provenance gate for grooming:** brainstorm/plan acting on an issue whose `authorAssociation` is not OWNER/MEMBER/COLLABORATOR requires explicit human confirmation; the body is ingested as quoted requirements via a credential-severed subagent (no Bash/gh/Write) when body-text reasoning is needed.
3. **Auto-add lands at stub only** (the pre-enabled "Item added" workflow targets `stub` after bootstrap — verify in the probe); ready-work additionally requires the in-repo join-keyed plan doc, so outsider issues dragged to `planned` are inert.
4. **Shell hardening:** slugify titles to `[a-z0-9-]` before branch names or shell strings; pass bodies via `--body-file`/stdin, never inline.
5. **Config trust:** preflight hard-fails unless the configured board owner equals the `origin` remote owner (allowlist + human confirmation for exceptions). Board-config values are validated against strict grammars (owner slug, integer number) before touching a shell line. The session cache file is gitignored.
6. **Token separation:** the upstream-scan routine's fine-grained PAT is never broadened with `project` scope — the injection-exposed scanner must not hold board-write capability. Local-dev note: `gh auth refresh -s project` broadens the cached OAuth token globally — accepted residual risk, recorded.
7. **In-script `gh` discipline:** the hook cannot see Python subprocesses, so `lifecycle_board.py` self-enforces explicit `--repo`/`--owner` on every call (unit test asserts no flagless invocations), mirroring upstream-scan Step 0.

### Resolution & modes (preflight + lifecycle_board)

`issue_tracker_resolved` becomes: **`github-project`** (committed board config present) | **`github`** (plain — today's semantics: `gh issue` + file-todos, no stage machinery, no board writes) | **`none`**. Beads/Linear leave the chain. No labels-stage mode — lifecycle features require a board; everything else degrades to today's behavior.

- **Committed board identity:** `github_project_owner:` + `github_project_number:` in a **committed** `agentic-engineering.md` at repo root (frontmatter, same flat-scalar grammar as the `.local` file; `.local` may override for testing). Untracked config broke fresh clones and worktree-isolated subagents. Preflight resolves config from the main repository root (`git rev-parse --git-common-dir`) so worktrees behave identically. Fix the local-config regex (`[A-Za-z]+` → allow hyphens) and `VALID_TRACKERS` — as written it silently ignores `github-project`.
- **Repo-scoped board reads (v1 topology stance: one board per repo).** Projects boards are owner-level and can hold many repos' issues. Every item read — ready-work, reconciler scope — filters `content.repository.nameWithOwner == origin` before any decision or write; the reconciler drops foreign items before `plan_repairs`. A shared/portfolio board is therefore read-tolerated but **never written to for foreign items** (repairs, comments, status moves stay in-repo). The join key normalizes internally to `owner/repo#N` and asserts repo == origin (the guard regex already admits the qualified form). Tier-1 mixed-repo fixture required.
- **Additional preflight hard errors** (each with `error_code` + named fix): `issues_disabled` (`hasIssuesEnabled` from already-fetched repo JSON), `unsupported_host` (gh auth host ≠ github.com — GHES lags the GraphQL surface), `insufficient_permission` (one GraphQL read: `projectV2.viewerCanUpdate` + repo `viewerPermission` — a contributor without project-write/triage gets a named error, not a half-executed claim). Fork-based contributors (origin = personal fork, board under the canonical owner) use the documented allowlist entry.
- **`--gate` emits provenance:** `author_association` + `provenance: trusted|untrusted` as output fields, so the security gate on outsider-authored issues is tier-1 testable rather than command prose.
- **`lifecycle_board.py`** — new importable module (underscored name; hyphenated scripts can't be imported), stdlib-only (no PyYAML; reuse the extracted frontmatter regex parser — currently duplicated in both scripts), Python ≥ 3.9 floor with the `Z`-suffix `fromisoformat` shim, string constants not `enum`. Pure decision core (`plan_repairs`, `evaluate_gate`, `decide_claim`, `merge_ready_legs` — injected `run_gh` callable, injected clock) + thin effectful wrappers. CLI verbs: `--gate <command> [--issue N]` (returns `{stage, issue, plan_doc, verdict, route}` with verdict ∈ `proceed | already_done | route_to_plan | route_to_work | claim_conflict | repair_needed | no_board`), `--claim <N>`, `--set-status <N> <stage>` (owns the four-ID flow; commands never hand-assemble GraphQL), `--ready-work`, `--reconcile`, `--doctor` (all A/B-class checks in report-everything mode — same check functions the hard-error paths use, so doctor and runtime can never disagree). `workflow-repo-preflight.py` stays a **read-only** thin CLI composing the module; it reports drift in JSON but repairs only under explicit `--reconcile` (which command entry gates pass by design; a human or CI can invoke it too).
- **Error contract:** failures emit `{ok: false, error_code, error, fix}` on stdout, exit 1 (two exit codes total; agents branch on `error_code`). Hard errors in `github-project` mode: gh missing/unauthenticated/missing scope/gh < 2.94.0/project not found/option missing after re-resolution — each with the named fix. **A failed ready-work query hard-errors; it never returns `[]`** (empty-on-error would silently idle orchestrate's dispatch loop forever). Individual repair failures degrade into `{repairs_applied, repairs_failed}`, never fail the command. Every `gh` call has a ~30s timeout (`gh_timeout` error code) and one jittered retry on 403/429.
- **Ready-work query** (the `bd ready` replacement) — constant-call composition: (1) one `gh project item-list --query "status:planned no:assignee" --limit 50` (server-side filter; **Phase 2 verification spike** — fallback is raw GraphQL requesting only item id + Status + issue number, max 2 pages); (2) ONE batched aliased GraphQL call fetching `blockedBy(first:1){totalCount}` for the ≤50 candidates. **2 API calls at any board size**; results sorted by Priority. Never enumerate the whole board; never per-issue `view` loops.
- **Reconciler** — scoped, batched, TTL-cached: scope = **origin-repo** items with Status ∈ {in_progress, in_review} + the session's join-keyed item (only stages with drift to repair); one batched aliased GraphQL cross-check (`state`/`stateReason`/`closedByPullRequestsReferences` + PR base branch for the flags); full scoped pass at most once per 10-minute TTL per session. **Cache file lives inside `$(git rev-parse --git-common-dir)/`** — untracked by construction, shared across worktrees, zero consumer `.gitignore` coordination; holds `last_reconciled_at` + session-resolved field/option IDs (no persistent ID cache; names re-resolve fresh per entry). Single-item reconcile for brainstorm/plan/compound; full pass for work/orchestrate (claim correctness); sub-agents inherit via the TTL. Steady-state entry budget: 2–4 calls / ~1–2s. Claim confirmation is **always a fresh read** — the TTL defers repairs, never claim-correctness.

## Technical Approach — Implementation Phases

Shipping shape: **two PRs** — Phase 1 (pure deletion, independently green), then Phases 2–5. Sub-issues decompose per checklist item.

### Phase 1: Linear removal (pure deletion, own PR)

- [x] Delete `commands/linear-{import,pull,status,sync}.md`; delete `skills/linear-sync/`
- [x] Delete `src/commands/linear.ts`, `src/sync/linear.ts`, `src/sync/linear-api.ts`, `src/types/linear.ts`; unwire `src/index.ts:7,20` (leave `tests/pi-writer.test.ts` — unrelated MCP fixture)
- [x] Strip Linear branches from kept files: `workflows/work.md:94-99,460-464`, `workflows/plan.md:179-180,641-649`, `workflows/review.md:262,381-394`, `triage.md:9-13,153-157,162-166`, `resolve_todo_parallel.md:22-25,49-51`, `skills/land-pr/SKILL.md:175`, `skills/setup/SKILL.md:124,151,167,175-182`, `skills/file-todos/SKILL.md:67-68,196-204` + template `linear_id`, `scripts/workflow-repo-preflight.py`, `scripts/plan-tracker-guard.py` (also removed the now-moot `issue_tracker_ambiguous`/`linear_api_key_present` preflight fields and their consumers)
- [x] Docs: plugin README (93–101, 129–132, 165), root README (37), `docs/index.html:877`, `docs/pages/getting-started.html:210-213` (manual); `bun run docs:build`; fix dangling `../linear-sync/SKILL.md` link in file-todos (removed with its section)
- [x] Counts **31→27 commands, 23→22 skills** in plugin.json + marketplace.json descriptions + all four README/index stat locations; version → 3.0.0 both files; CHANGELOG `[Unreleased] — 3.0.0` breaking-change entry
- [x] `bun test` (378 pass) + `python3 -m unittest discover -s plugins/agentic-engineering/tests -p '*_test.py'` (14 pass) green

### Phase 2: lifecycle_board module, preflight, guard, hooks (Python — tiered tests)

- [x] **Prerequisite (blocker):** upgrade dev `gh` to ≥ 2.94.0 (2.79.0 → 2.96.0 via brew); explicit gh 2.96.0 pin added to `.github/workflows/ci.yml`; fixtures recorded from the 2.96.0 binary. Live-verified: `--parent`, `--blocked-by`, `--add-blocked-by`, `item-list --query`, and `--json blockedBy/blocking/parent` all present
- [x] New `scripts/lifecycle_board.py` per Architecture: pure decision core (`evaluate_gate`, `decide_claim`, `plan_repairs`, `merge_ready_legs`) + injected `run_gh`; CLI verbs `--gate/--claim/--set-status/--ready-work/--reconcile/--doctor`; error contract `{ok, error_code, error, fix}`; in-script `--repo`/`--owner` discipline; dataclasses via `asdict`; shared frontmatter parser
- [x] `workflow-repo-preflight.py`: resolution enum (`github-project`/`github`/`none`), committed-config resolution via git-common-dir (worktree-safe), hyphen-tolerant config regex + `VALID_TRACKERS`, owner-equals-origin validation (hard error), composes lifecycle_board read-only (repairs only under `--reconcile`); `beads_remember_available` kept; tracker banner survives. *(`issues_disabled`/`unsupported_host`/permission checks live in `--doctor` and the effectful verbs' error paths; per-entry preflight probes deferred to Phase 3 wiring where commands consume the verbs.)*
- [x] Repo scoping + flags: item reads filter foreign repos before decisions/writes; join-key normalization to `owner/repo#N`; reconciler `flags` channel (`merged_to_non_default_branch`, `stale_join_key`, `truncated_ready_work`) with issue comments; `--gate` emits `author_association`/`provenance`
- [x] Session TTL cache **in `--git-common-dir`** (untracked by construction): `last_reconciled_at` + schema IDs; batched-GraphQL helper; 403/429 jittered single retry; **`item-list --query` spike resolved: supported on gh 2.96 / github.com** (raw-GraphQL fallback unneeded)
- [x] `plan-tracker-guard.py`: `TRACKER_FIELDS` → `("github_issue",)`; regex `\d+ | org/repo#\d+`; remediation gh-only; `issue_tracker: none` carve-out kept; scope stays `docs/plans/`; `bead_id`-alone now blocks (12 tests)
- [x] `.claude/hooks/block-upstream-pr.sh` extended: `gh project` writes (15-subcommand list), ProjectV2-mutation GraphQL, `GH_REPO=` prefix, REST writes to upstream paths (30 hook tests) + committed `tests/flagless-gh.test.ts` (fence-aware, continuation-joining, 2-entry allowlist for legacy lines Phase 3 rewrites)
- [x] **Tests**: 94 python (12 guard + 30 hook + 6 gh-contract incl. live JSON-shape probes + 8 preflight + 38 lifecycle: gate/claim/closed-five-repair tables with merge-queue `merged==false`, assignee-anchored, human-drag and abandoned-never-promoted negatives; mixed-repo scoping; Priority sort; truncation; 2-call budget via argv-validating fake; owner-mismatch/allowlist) + 380 bun; recorded fixtures in `tests/fixtures/gh/` with `.meta` provenance (project fixtures marked `.skip` until Phase 4 bootstrap)

### Phase 3: Command & skill rewrites (writer contracts + uniform gates)

- [ ] **New `skills/lifecycle/SKILL.md`** (`user-invocable: false`; must NOT set `disable-model-invocation` — commands load it): the 9-stage enum + semantics (sole definition), writer table, entry-gate pattern + verdict routing, claim semantics, "create→board-add→set-status is one sequence; use `--set-status`, never raw item-edit", modes + join-key contract; `references/gh-recipes.md` for gh invocation details. **Fix the latent identical bug: `skills/file-todos/SKILL.md` sets `disable-model-invocation: true` yet review.md must load it**
- [ ] Every rewritten command gets the uniform 3-part entry gate: writer-contract line ("this command performs exactly one transition: X → Y") + one `--gate` invocation + closed verdict branch table (explicit imperative + STOP/continue per branch; predicates on named enum values, never prose). Orchestrate's State Detection §111–125 collapses to `--gate orchestrate` (artifact heuristics only when `verdict == no_board` or un-keyed legacy docs)
- [ ] `workflows/plan.md`: Step 7 → issue create/update + sub-issues (`gh issue create --parent`) + dependencies (`--blocked-by`) + board add + `--set-status planned`; templates drop `status:`; brainstorm matching via join key (14-day heuristics only as legacy fallback); Post-Generation precondition checks `github_issue` only
- [ ] `workflows/work.md`: Phase 1 = `--claim`; Phase 2 loop over sub-issues; Phase 3 gate "no open sub-issues"; Phase 4 rewritten (PR with `Closes #N`, `--set-status in_review`, issue NOT closed — replace the "PR creation is the completion event" rationale with automation-owns-shipped; delete `work.md:444-447`, the `status: completed` frontmatter writer); Orchestrated Execution bindings table → single GitHub binding; beads reduced to the opt-in scratchpad note
- [ ] `workflows/brainstorm.md`: entry gate; on completion create/update issue + `--set-status brainstormed` + write `github_issue` into doc frontmatter; "Capture as bead" removed
- [ ] `workflows/review.md`: beads branch deleted; file-todos path kept for findings; `workflows/compound.md`: conditional `--set-status compounded` (join key present only); `bd remember` kept; `workflows/merge.md` wording
- [ ] `triage.md`: creates issues at stub (todo-file flow intact). **`upstream-scan.md`:** extend `allowed-tools` with `Bash(gh project *)`, amend its Invariants ("only permitted writes…") + Success Criteria ("zero writes outside `$REPORT_REPO`") for board adds, add graceful degradation for scheduled runs missing `project` scope, and update its now-stale gh-safety prose (the hook now covers `gh issue`; explicit-`--repo` is no longer a deviation). `report-bug.md`: unchanged (not a lifecycle writer)
- [ ] `skills/land-pr/SKILL.md:170-177`: the whole tracker-close dispatch (not just the Linear line) → **invoke the shared `--reconcile`** to verify/repair shipped — never a second reconcile implementation; PR-body projection block **dropped** (GitHub renders the linked issue + board natively; reconciler comments are the provenance trail)
- [ ] `allowed-tools` pass: workflow commands gain `Bash(gh issue *), Bash(gh project *), Bash(python3 *)`; **raw `Bash(gh api graphql *)` is grantable only in the user-gated setup skill** — commands route GraphQL through `--set-status`; workflow commands stay model-invocable (orchestrate invokes them; idempotent gates are the stated rationale in each description)

### Phase 4: Bootstrap & external wiring

- [ ] **Bootstrap script** (hosted by setup skill, but a script — testable): `gh project create` with **`--owner` derived from the origin remote owner** (never `@me` — on an org repo that creates a user-owned project the plugin's own owner-check then rejects) → read Status field + default option IDs by name → **fresh-project guard: hard-stop with a printed diff unless the current option set is exactly GitHub's defaults (Todo/In Progress/Done) or exactly the canonical 9** (never "adopt" a customized project — the replace-all mutation would silently destroy a consumer team's existing options/automations) → ONE `updateProjectV2Field` call sending all 9 options **with default IDs attached** (Todo→stub, In Progress→in_progress, Done→shipped) + the Priority field → **disable the "Item reopened" workflow** (`deleteProjectV2Workflow` — otherwise reopening an issue stamps `stub`, erasing lifecycle position) → verify the remaining pre-enabled workflows are `enabled: true` → write owner/number to committed `agentic-engineering.md`. **Idempotency rule: on re-run, re-read current options and pass every existing option's `id` — never send a partial or id-less list** (verified destructive). Golden-fixture test on the GraphQL documents; live idempotency test (run twice, 9 options + workflows intact). Refuses to run with `GH_REPO`/`GH_HOST` overrides present
- [ ] **Scripted verification probe** (agent-executable, poll ≤60s): create scratch issue → board-add → close → assert Status=shipped → reopen/abandon-path assert → capture evidence (issue #, observed flip) as an acceptance checkbox
- [ ] **Manual checklist** (the only two UI-only steps): configure auto-add-from-repo (verify it lands items at `stub`); create the ready-work saved view (`status:planned no:assignee`, sorted by Priority) with a description noting it over-shows blocked items — check Blocked-by on the issue before starting. Also enable built-in **auto-archive** for terminal stages (keeps the active board under the ~200-item GraphQL comfort zone permanently)
- [ ] **`deployed` pattern doc** (consumer repos): workflow snippet using a **GitHub App installation token** (recommended) or dedicated-machine-account PAT in an environment-scoped secret; **comment-always / Status-best-effort** semantics (bounded poll ≤90s, then post the deploy-evidence comment regardless — see the writer table); **the SHA→issues mapping recipe** (`repos/{o}/{r}/commits/{sha}/pulls` → `closingIssuesReferences`, iterated over the deploy range since the last deploy — a deploy carries several PRs, not one); the **`on: deployment_status` adapter** for external CD that creates GitHub Deployment records (Vercel, Cloudflare Pages yes; Netlify/Railway/Fly.io generally no — those repos ignore the stage); environment filter (`state == success && environment == Production` — staging/dev jobs never call the stamper); **build-vs-promotion distinction (verified):** Vercel fires `deployment_status: success` at *build* completion, NOT at promotion — repos that stage builds and promote manually must instead trigger on **`vercel.deployment.promoted`** via Vercel's official `repository_dispatch` integration (`vercel/repository-dispatch`; `on: repository_dispatch: types: ['vercel.deployment.promoted']`), or the stamp lies by hours/days; **minimal-adapter note:** the deploy-evidence *comment* needs only `GITHUB_TOKEN` (issues-write) — the App/PAT token is required only for the optional best-effort Status write, so promotion-flow repos where compound usually wins the race can ship a comment-only adapter with zero extra secrets; explicit "GITHUB_TOKEN cannot write the board — fail loudly when the secret is missing (Status-write variant only)"; secret never in repo/config/issue bodies
- [ ] **Git-flow issue-closer snippet** (consumer docs): the ~10-line `on: pull_request closed` workflow against non-default integration branches — if merged, `gh pr view --json closingIssuesReferences` → `gh issue close` each. **Plain `GITHUB_TOKEN` suffices** (closing issues is repo-scoped; the board automation does the rest) — the escape hatch for the `merged_to_non_default_branch` flag
- [ ] **New command `commands/lifecycle-doctor.md`** — the setup/compatibility verification front door, run before the first real work item and re-runnable any time. Wraps `lifecycle_board.py --doctor` and renders a PASS/WARN/FAIL/SKIP checklist with a named fix per finding, ending with an explicit **"Ready for first work item: yes/no"**. Check groups:
  - *Local toolchain:* gh installed, ≥ 2.94.0, authenticated, `project` scope, host == github.com, `python3` ≥ 3.9, plugin scripts reachable
  - *Repo shape:* issues enabled, committed board config present + parseable, board owner == origin owner, `viewerPermission` ≥ triage, fork-trap hooks pinned (this-repo), default branch resolvable
  - *Board schema:* project exists + `viewerCanUpdate`, Status field carries exactly the canonical 9 options, Priority field present, "Item closed" workflow enabled, "Item reopened" workflow disabled, auto-archive enabled (WARN if not), auto-add + saved view (SKIP-with-manual-checklist-pointer where the API can't read them)
  - *Delivery topology (detection, not enforcement):* recent merged PRs target the default branch (WARN → git-flow closer-workflow guidance); GitHub Deployment records present → names the matching `deployed` adapter (build-success vs `vercel.deployment.promoted` promotion flow, per the pattern doc); adapter workflow file present if config claims deploy stamping; secrets are unreadable by design → SKIP with "verify in repo settings" note
  - *`--live` flag (optional, opt-in):* the scratch-issue probe (create → board-add → close → assert `shipped` → cleanup) + bootstrap idempotency dry-run — the same tier-3 machinery, run on demand, evidence printed
  - Frontmatter: user-invocable; read-only `allowed-tools` (`Bash(gh *)` reads + `Bash(python3 *)`); `--live` is the only path that creates anything, and it cleans up after itself
- [ ] Setup skill records mode + writes the committed config (session cache needs no gitignore — it lives in `--git-common-dir`)

### Phase 5: Docs, diagrams, consistency, versioning

- [ ] `FLOWS.md`: redraw around the lifecycle; add a mermaid `stateDiagram` (including the five repairs and terminal refinements) as the canonical visual
- [ ] Plugin README: lifecycle table, board setup, human claim path ("assign yourself + drag to in_progress — the drag is the claim"), card-order-is-decorative note, beads-scratchpad note; `bun run docs:build`; CHANGELOG
- [ ] **README "What this plugin assumes about your repo"** — the eyes-wide-open contract (D-class register rows): one board per repo; default-branch merges drive `shipped` (git-flow → the closer workflow, or cards stall with a reconciler comment); issues enabled; issue text is untrusted data; board is agent-managed after bootstrap (fresh-project guard, don't rename options); github.com only, gh ≥ 2.94.0 + `project` scope, project-write + triage permission; GitHub Free suffices for single-repo (its one auto-add workflow is all we use); macOS/Linux/WSL (native Windows untested); fork-based contribution needs the owner-allowlist entry
- [ ] **README "Delivery-topology assumptions"** — per-topology expectations (from the state-flow review): trunk-based CD (deployed nearly redundant — fine to ignore), multi-environment (`deployed` = production only; staging never stamps), git-flow (stall + fix), release trains/libraries (`shipped` = "merged to default branch," NOT "in users' hands"; optional release-tag stamping), external CD (deployment_status adapter where Deployment records exist), no-deploy repos (`shipped → compounded` is the intended path); `deployed` is a high-water mark — rollbacks never move the board backward
- [ ] **Counts after PR 2: 28 commands / 23 skills** (new `lifecycle-doctor` command; new `lifecycle` skill offsets the deleted `linear-sync`) — update all description strings + tables again
- [ ] **README "Verify your setup"** section: run `/lifecycle-doctor` after install/bootstrap and before the first work item; re-run after changing board config, tokens, or CD wiring; `--live` for the full end-to-end probe
- [ ] **Versioning policy:** both PRs share one CHANGELOG `[Unreleased] 3.0.0` entry; PR 1 sets the version fields; PR 2 amends the same entry (no second major bump); **no marketplace release/tag between the two merges**
- [ ] Migration: **grandfather** — the in-flight plan (`github_issue: 28`) already carries the join key; legacy `status:`/`bead_id:` fields ignored and removed on next command touch; no one-shot script

## Test Strategy (four tiers)

**Design rule enabling all of it:** every lifecycle predicate — gate evaluation, claim decision, repairs, ready-work — is a pure function in `lifecycle_board.py` taking parsed `gh` JSON and returning a decision; command markdown only invokes verbs and branches on verdicts. Logic left in prose is untestable by construction.

- **Tier 1 — Hermetic unit (CI, per-PR, no gh):** `lifecycle_board_test.py` + rewritten `plan_tracker_guard_test.py` (unittest, subprocess/tempdir conventions). Decision tables for: resolution enum + config parsing + owner validation; gate verdicts (planned-no-doc → route_to_plan; ≥planned+doc → proceed/already_done); claim (sole-assignee, multi-assignee back-off, blocked-by refusal); the **closed five-repair set** including all never-repair negative cases; ready-work merge + Priority sort; call-count budgets (ready-work ≤ 2; warm-TTL reconcile = 0; no unfiltered item-list ever). Mocks replay **recorded fixtures only** and fail on unexpected argv.
- **Tier 2 — gh contract (CI, per-PR, real gh, no PAT):** `gh_contract_test.py`. (a) Flag-surface pinning: table-driven `gh <cmd> --help` assertions for every flag the plugin uses (`--parent`, `--blocked-by`/`--add-blocked-by`, `item-list --query`, item-edit's four IDs, `issue list --json` dependency fields via the invalid-field error enumeration) + `gh --version` ≥ 2.94.0; loud skip locally when gh is absent, required in CI. (b) Read-only JSON-shape probes with Actions' `GITHUB_TOKEN` (it CAN read issues/PRs — only Projects is off-limits): assert `stateReason` casing and `closedByPullRequestsReferences`/`mergedAt` shapes against this repo's own history (e.g., issue #28's merged PR); auto-skip unauthenticated.
- **Tier 3 — Scheduled live smoke (nightly, PAT/App secret, not PR-blocking):** persistent scratch project (automations enabled once via bootstrap — doubles as the living verification probe): scripted board mechanics walk; automation flip on close (poll ≤60s); live reconciler repair of a not-planned close; ready-work returns planted planned/unassigned/unblocked item and excludes the planted blocked one; bootstrap re-run idempotency (9 options + workflows intact). Failures open an issue; cleanup deletes scratch items. Also proves the documented consumer `deployed` credential pattern.
- **Tier 4 — Runbook (manual, release gate for 3.0.0, checked off in the PR):** R1 full pipeline via the real commands (triage→brainstorm→plan→work→PR→merge→compound, every gate observed); R2 re-entry idempotency (brainstorm ×2 routes to plan; plan ×2 updates without duplicates); R3 true concurrent claim race (two sessions, one proceeds, loser visibly backs off); R4 human drags a card mid-command → next gate + reconciler respond per Lifecycle rules.

## Alternative Approaches Considered

- **Two-dimension state (grooming × lifecycle):** rejected — gates would consult two fields; most combinations nonsensical (see brainstorm).
- **Beads as pane, GitHub→beads sync:** rejected — humans/browsers are first-class; custom sync machinery vs. free automations (see brainstorm).
- **Custom "Stage" field:** rejected — forfeits built-in automations (correction #1).
- **`stage:*` labels fallback mode:** rejected during deepening — a second untested state machine with a zero-writer `shipped`; plain `github` mode preserved instead.
- **Deprecate-and-extract Linear:** rejected for deletion — git history is the archive.
- **Event-driven sync:** structurally unavailable — `projects_v2_item` webhooks are org-level only; user-account projects have no eventing, so poll-on-entry is the architecture, not a compromise.

## System-Wide Impact

### Interaction graph
Command entry → `--gate` (read + scoped `--reconcile`) → verdict branch → the command's one owned transition via `--set-status`/`--claim` → built-in automations react to issue closes → next entry re-reads. Stop hook fires on plan writes; SessionStart/PreToolUse hooks + in-script discipline gate `gh` writes. No repo-level Action reacts to board changes (impossible on user accounts).

### Error & failure propagation
Preflight hard-errors with `error_code` + named fix (never silent mode fallback — mode comes from committed config). Ready-work never returns empty on error. Repair failures degrade into reported JSON, never fail the command. Rate limits: primary GraphQL budget comfortable after scoping (~50–100 calls per 4-agent wave vs ~700 unscoped); binding constraints are secondary limits (~80 mutations/min shared, 2k pts/min) — mitigated by TTL cache, batched aliased reads, jittered retry; claim confirmation always fresh.

### State lifecycle risks
Partial create→board-add→set-status sequences: creator commands run the sequence atomically-in-order; the reconciler treats join-key-referenced off-board issues as repairable drift. The any-close→shipped automation lie is repaired by rule 2. The "Auto-close issue" workflow (Status=shipped ⇒ issue closes) is convergent, not drift — reconciler must not "repair" it. Bootstrap's id-less option update is the one destructive foot-gun — guarded by the idempotency rule + golden tests + live idempotency check.

### API surface parity
One vocabulary (the lifecycle skill), one binding (GitHub), one implementation of every predicate (lifecycle_board). Humans and agents have parity on every capability: view ready work (saved view / `--ready-work`), claim (assign+drag / `--claim`), move stages (drag / `--set-status`), reconcile (comment trail / `--reconcile`), verify setup (probe script, both audiences).

## Portability & Assumptions Register

Every assumption the design makes about a consumer repo, with its verification class: **A** = runtime preflight hard-error · **B** = bootstrap/probe at setup · **C** = tests (tier 1–3) · **D** = documentation-only (the eyes-wide-open class — shipped in the two README sections above). **`/lifecycle-doctor` is the on-demand runner for every A- and B-class row** (same check functions as the runtime hard-errors, report-everything mode) and *detects* the two biggest D-class rows (non-default-branch merges, deployment topology) as WARNs with guidance — run it before the first real work item.

| Assumption | Class | Verified by / failure behavior |
|---|---|---|
| One board per repo; board holds only this repo's issues | **C + D** | Repo-scoped reads make violation harmless (foreign items filtered, never written); mixed-repo tier-1 fixture; README states the v1 stance |
| PRs merge into the default branch (`Closes #N` → close → `shipped`) | **C-flag + D** | `merged_to_non_default_branch` reconciler flag + issue comment naming the fix; tier-3 exercises the real `Closes #N` path; README topology section |
| `shipped` means "merged to default branch," not "in users' hands" | **D** | Definitional — README topology section; release-train repos read it eyes-open |
| `deployed` = production only, high-water mark, optional | **D** | Lifecycle skill normative sentence; stamper doc (comment-always); staging never stamps |
| Board owner == origin owner; operator has project-write + triage | **A** | `owner mismatch` / `insufficient_permission` hard errors (viewerCanUpdate + viewerPermission probe); fork workflow via documented allowlist |
| Repo has issues enabled | **A** | `issues_disabled` hard error (hasIssuesEnabled, already-fetched JSON) |
| github.com host (not GHES) | **A** | `unsupported_host` hard error |
| gh ≥ 2.94.0 with `project` scope everywhere commands run | **A + C** | `gh_version`/scope hard errors; tier-2 flag pinning; CI pin |
| Bootstrap targets a fresh project (or its own prior output) | **B** | Fresh-project guard: hard-stop + printed diff on unrecognized option sets — never destroys a consumer's existing board |
| Status options keep the canonical 9 names post-bootstrap | **A** | Per-entry name re-resolution → `option missing` hard error with named fix |
| Auto-add lands new issues at `stub` | **B** | Setup probe; re-checkable; plan-doc gate makes violations inert for `work` regardless |
| Join key `github_issue` resolves to a live issue in this repo | **A-flag** | Normalized to `owner/repo#N`, asserted against origin; `stale_join_key` flag on 404/transfer |
| Ready-work candidates fit the 50-item cap | **C-flag** | `truncated_ready_work` flag when the cap is hit |
| Actions `GITHUB_TOKEN` never writes the board | **C + D** | Tier-3 proves the App-token pattern; docs mandate fail-loudly when the secret is missing |
| POSIX environment (`python3`, bash hooks) | **D** | README support matrix: macOS/Linux/WSL; native Windows untested |
| GitHub Free tier suffices (single auto-add workflow) | **D** | README sentence tied to the one-board-per-repo stance |
| Shared user token across repos/agents stays under secondary limits | **C + D** | Call-budget tests single-repo; jittered retry then named error — degrade, never corrupt |

## External System Wiring

**REQUIRED.**

- **GitHub Projects v2 board** (user project under the repo owner): created + configured by the bootstrap script (project, 9 Status options ID-preservingly, Priority field); five built-in workflows arrive pre-enabled and survive bootstrap (verified by execution). **Manual (no API): auto-add-from-repo config + saved-view creation.** Scripted probe verifies the automation flip and records evidence.
- **`gh` CLI ≥ 2.94.0 with `project` scope** on every dev/agent machine (`gh auth refresh -s project`); verified by preflight; pinned in CI. **Local machine currently at 2.79.0 — upgrade is a Phase 2 blocker.**
- **Consumer-repo deploy stamping** (documented pattern): GitHub App installation token (recommended) or dedicated-machine-account classic PAT in an environment-scoped secret; guarded write; fails loudly when the secret is missing.
- **Fork-trap guardrails:** extended hook (owner-validated `gh project`/GraphQL, `GH_REPO=`, REST writes) + committed flagless-gh grep test + in-script `--repo` discipline (the hook cannot see subprocesses).

## Acceptance Criteria

### Functional
- [ ] Board (Status 9 options + Priority) is the source of truth; every transition performed by its designated writer **or the shared reconciler applying one of the five documented repairs**
- [ ] All workflow commands + triage/upstream-scan gate on entry via `--gate` and route around completed stages (runbook R1–R2)
- [ ] Claim protocol survives concurrent claims (tier 1 decision test + runbook R3); blocked items never claimed; yield decisions assignee-anchored
- [ ] Reconciler repair set is **closed at five** (tier-1 negative cases incl. merged==false, non-assignee PR, foreign-repo items) and every repair posts an issue comment; the three report-only flags emit comments + JSON, never writes
- [ ] All board reads are repo-scoped (`content.repository.nameWithOwner == origin`); a mixed-repo board fixture shows foreign items filtered and never written
- [ ] Bootstrap refuses non-fresh projects with a printed diff; derives owner from origin; disables "Item reopened"; run-twice idempotency keeps 9 options + workflows intact
- [ ] Ready-work: planned ∧ unassigned ∧ unblocked, Priority-sorted, ≤ 2 API calls at any board size; hard-errors rather than returning empty on failure; truncation flagged at the 50-cap
- [ ] Command-entry overhead ≤ ~2s / ≤ 5 `gh` calls steady-state; warm-TTL entries skip reconciliation
- [ ] Security invariants present in the lifecycle skill + rewritten commands (untrusted-content rules, authorAssociation gate, no comment reads)
- [ ] Linear: zero references outside CHANGELOG/git history; beads: no gate reads a bead; `bd remember` still works; `github` plain mode + `none` degrade as today

### Quality gates
- [ ] `bun test` green (counts 27/22 after PR 1, **28/23 after PR 2**; version parity 3.0.0; docs:check; new flagless-gh grep test)
- [ ] `/lifecycle-doctor` reports all-PASS on this repo (with `--live` evidence) before the runbook executes — the doctor is the runbook's step 0
- [ ] `python3 -m unittest` green: tier 1 + tier 2 (help-text leg mandatory in CI at pinned gh ≥ 2.94.0; token-probe leg auto-skips unauthenticated) + hook tests
- [ ] Nightly tier-3 smoke workflow committed and green once before the PR-2 merge; bootstrap idempotency + automation-probe evidence recorded in the PR body
- [ ] Runbook R1–R4 executed and checked off before tagging 3.0.0
- [ ] FLOWS.md renders; docs regenerated; CHANGELOG documents breaking changes + migration

## Dependencies & Risks

| Risk | Mitigation |
|---|---|
| ~~Automation can't target custom options~~ **RESOLVED** — verified by live execution (ID-preserving `updateProjectV2Field` keeps workflows enabled and targeting renamed options) | Bootstrap idempotency rule + golden tests + live probe as regression insurance |
| Bootstrap id-less option update destroys automations/values (verified destructive) | Always pass existing option `id`s; golden-fixture + run-twice live test |
| Any-close→shipped mislabel | Reconciler repair 2 (stateReason); tier-1 + tier-3 coverage |
| `gh project item-list --query` unsupported on some surface | Phase 2 verification spike; raw-GraphQL minimal-fields fallback; tier-2 flag pinning catches drift first |
| gh < 2.94.0 in dev/CI (local machine is 2.79.0 today) | Phase 2 blocker: upgrade + CI pin; preflight hard-error `gh_version` |
| Untracked config breaks clones/worktrees | Board identity in committed config; git-common-dir resolution; tier-1 worktree case |
| Prompt injection via issue content | Security invariants 1–4; credential-severed body reads; grep-testable no-comment-reads rule |
| Token blast radius (classic PAT) | App installation token recommended; machine-account + environment-scoped secret fallback; scanner/board token separation |
| Multi-agent secondary rate limits (~80 mutations/min shared) | Scoped reconciler + TTL cache + batched reads + jittered retry |
| Reconcile TTL serves stale state to a claimant | Claim confirm is always a fresh read; TTL defers repairs only |
| Board grows past ~200 active items | Auto-archive built-in workflow for terminal stages |
| Git-flow / non-default-branch merges stall items at in_review silently | `merged_to_non_default_branch` flag + comment; documented GITHUB_TOKEN-only closer workflow |
| Shared/portfolio board → plugin writes on foreign repos' issues | Repo-scoped reads everywhere; foreign items dropped before repairs; v1 stance documented |
| Bootstrap aimed at a consumer's existing team board destroys their options | Fresh-project guard: hard-stop + diff unless options are GitHub defaults or the canonical 9 |
| Reopened issues stamped back to `stub` by the pre-enabled workflow | Bootstrap disables "Item reopened"; re-staging is a deliberate operator move |
| `deployed` never lands because compound wins the timing race | Comment-always stamper: deploy evidence survives as the issue-comment trail; Status write best-effort |
| MAJOR churn for plugin consumers | Single 3.0.0 release window; Phase 1 as its own reviewable PR; CHANGELOG migration section |

## Future Considerations (deferred, tracked as follow-ups)

Review findings as sub-issues (todos/*.md kept this iteration); stale-claim flagging + reaper Action (deferred together); `stage:*` labels mode if a boardless consumer ever asks; org-level Issue Fields if the repo moves to an org; webhook-relay eventing if poll-on-entry proves insufficient.

## Sources & References

### Origin
- **Brainstorm:** [docs/brainstorms/2026-07-05-unified-lifecycle-github-projects-brainstorm.md](../brainstorms/2026-07-05-unified-lifecycle-github-projects-brainstorm.md) — single lifecycle enum, one-writer-per-transition, GitHub Projects as single pane, beads demotion, Linear removal. Amended by Design Corrections 1–6 and the deepening revisions above.

### Internal (verified line references)
- Tracker resolution: `plugins/agentic-engineering/scripts/workflow-repo-preflight.py:137-202` (config regex at 156); Stop hook: `scripts/plan-tracker-guard.py:16,28-33,136,157`
- Dispatch surfaces: `commands/workflows/plan.md:173-183,607-718`; `work.md:89-200,440-471,485-601`; `orchestrate.md:111-125`; `review.md:232-262,381-394`; `upstream-scan.md:6,31-36`
- Consistency machinery: `tests/plugin-consistency.test.ts`; `scripts/generate-docs.ts`; semver rules in `plugins/agentic-engineering/CLAUDE.md`; CI discovery pattern `.github/workflows/ci.yml:28`
- Latent frontmatter bug to fix in passing: `skills/file-todos/SKILL.md:4` (`disable-model-invocation: true` vs review.md dependency)

### External (verified 2026-07; ★ = confirmed by live execution on scratch projects)
- ★ `updateProjectV2Field` edits built-in Status options; replace-all with `id` escape hatch: docs.github.com/en/graphql/reference/mutations#updateprojectv2field; changelog 2024-12-12; option-orphaning: github.com/orgs/community/discussions/198803
- ★ Fresh projects ship five enabled Status workflows; ID-preserving rename keeps them enabled; id-less replace silently disables them
- Built-in automations UI-only (no create/enable API; `deleteProjectV2Workflow` is the sole mutation): …/using-the-built-in-automations
- GITHUB_TOKEN cannot access Projects / Actions pattern / App-token recommendation: …/automating-projects-using-actions
- Sub-issues GA + REST: github.blog/changelog/2025-04-09; docs.github.com/en/rest/issues/sub-issues — Issue dependencies GA: github.blog/changelog/2025-08-21 — gh CLI ≥ 2.94.0 surface: github.blog/changelog/2026-06-10
- gh project manual (item-edit four-ID flow, `--query`, `project` scope; no field-edit): cli.github.com/manual/gh_project
- Multi-agent claiming + race modes: github.blog Copilot coding agent + multi-agent workflow engineering posts
- GraphQL rate/secondary limits: docs.github.com/en/graphql/overview/rate-limits-and-node-limits-for-the-graphql-api; >200-item query timeouts: github.com/cli/cli/issues/13432

### Related work
- In-flight plan to grandfather: docs/plans/2026-07-02-feat-upstream-source-adoption-tracking-plan.md (`github_issue: 28`) — also the source of the ported security-invariant pattern
