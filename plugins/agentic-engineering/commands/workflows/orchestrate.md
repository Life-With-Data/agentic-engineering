---
name: workflows:orchestrate
description: Drive the brainstorm → plan → work → review → land → compound pipeline as the orchestrator — delegating implementation to sub-agents, reviewing their work, and running fully autonomously by default (surfacing only genuine blockers; --final-review adds one pre-merge check). Segment flags bifurcate the run — --groom stops once the item is planned; --implement starts from groomed work and refuses to groom.
argument-hint: "[feature idea, or path to an existing brainstorm/plan] [--groom | --implement] [--final-review | --steer | --careful]"
disable-model-invocation: true
---

# Orchestrate the Agentic Engineering Pipeline

**Note: The current year is 2026.**

You are the **orchestrator** sitting between the user and the workflow pipeline. The user has a flow they run by hand:

```
/workflows:brainstorm → /workflows:plan → [/deepen-plan?] → /workflows:work → /workflows:review → /workflows:compound
```

The full expansion — including the finalization steps — is:

```
brainstorm → plan → [deepen-plan?] → work (→ PR) → review → [resolve findings]
           → [test-browser] → [feature-video] → [land-pr: CI green + merge]
           → compound → [land-docs: docs-only PR merged on green]
```

Your job is to **run that flow for them** — handling every menial transition automatically while reaching out **only when the user's judgment is genuinely required**. Think of yourself like `/goal` or `/loop`: you keep the work moving on your own, and you interrupt the user for steering, not for chores.

The contract, stated plainly:

> **The orchestrator is a reviewer, not an implementer. Delegate the work to sub-agents, review what comes back, keep the pipeline moving, and surface to the user only genuine blockers — running the whole pipeline to a merge on its own by default.**

This command spans the full autonomy spectrum. **The default is fully autonomous:** no human in the loop, no approval prompts — the orchestrator self-answers every intermediate judgment call (recording each in a decision log), merges once the PR is landable, and surfaces *only* genuine blockers. From there each flag adds human involvement: **`--final-review`** keeps the autonomous run but pauses exactly once, at the **Final-Review gate**, before the merge; **`--steer`** restores the classic human-checkpoint cadence for runs the user wants to drive; **`--careful`** confirms at every stage boundary on top of that.

## Input

<input> #$ARGUMENTS </input>

Parse the input:

- **A feature idea / description** (free text) → a new run; start from the earliest pipeline stage that fits (see State Detection).
- **A path to a brainstorm or plan** (`docs/brainstorms/*.md` or `docs/plans/*.md`) → resume from that artifact.
- **Empty** → detect in-flight work from artifacts (see State Detection) and resume; if nothing is in flight, ask the user once: *"What would you like to build? Describe the feature, or point me at an existing brainstorm/plan."*

**Autonomy flag** (optional, anywhere in the input):

| Flag | Behavior |
|------|----------|
| _(default)_ | **Fully autonomous.** The orchestrator runs the pipeline end-to-end with **no approval prompts of any kind**: it delegates implementation to sub-agents, reviews their work itself, self-answers the intermediate judgment gates (approach, plan approval, findings triage) — logging each call in the **decision log** — and, once CI is green, the independent review ran with P1s resolved, threads are resolved, and the PR is mergeable, `land-pr` merges with no prompt (the review packet becomes the final summary). It surfaces to the user for **genuine blockers only** (material scope change, branch protection, unresolvable ambiguity) — the universal floor that applies in every mode. Built for unattended runs (cron routines, overnight loops) where a paused gate means the work just sits. |
| `--final-review` | **Autonomous, with one pre-merge check.** Identical to the default in every respect — same sub-agent delegation, same self-answered intermediate gates, same decision log — **except** it pauses exactly once, at the **Final-Review gate**, and presents the review packet for your go before merging. Use it when you want the hands-off run but the final merge to be your call. |
| `--steer` | **Steer mode** (the classic cadence). Stop at the defined checkpoints below (approach, plan approval, findings triage, merge) and at blockers. Auto-handle all menial transitions. |
| `--careful` | Pause for a quick confirmation at **every** stage boundary, plus all steer-mode checkpoints. |

Autonomy ordering (most to least human involvement): `--careful` > `--steer` > `--final-review` > _(default, fully autonomous)_. Each step removes gates; the default removes the last one (Final-Review), leaving only the universal blocker floor. `--auto` is accepted as an explicit alias for the default. Announce the resolved mode (and segment, if any) in your opening status line.

**Pipeline segment flag** (optional, orthogonal to the autonomy flags — at most one):

| Flag | Segment |
|------|---------|
| _(default)_ | The full pipeline, end to end. |
| `--groom` | **Intake → groomed, then stop.** Run only the grooming segment (brainstorm → plan) and end the run once the item is `planned` with a join-keyed plan doc and sub-issues. `/workflows:groom` is the standalone form of this segment and its spec is **normative** here — same routing ladder, same hard-stop contract, same groomed packet. Items already at or past `planned` report as already-groomed / past-grooming and stop. |
| `--implement` | **Groomed → shipped.** Require the item to already be groomed: if the board stage resolves below `planned` — or Status says `planned` but no join-keyed plan doc exists — **stop and route to `/workflows:groom`**. An implement run never grooms as a side effect; the bifurcation exists so grooming can be reviewed (or supervised) separately before code gets written. From `planned`, run the remaining pipeline exactly as the default does (plan self-review at pickup, then work → review → land → compound). |

Segment flags compose with autonomy flags: `--groom --steer` is an interactive grooming session; `--implement` alone is the classic unattended build from a ready backlog. Under `--groom` there is no merge, so `--final-review` is a no-op. Together the pair supports the standard bifurcated flow — groom intake into a ready backlog first, implement from it later: `--implement` with empty input pulls from `--ready-work` as usual, whose items (`planned ∧ unassigned ∧ unblocked`) are groomed by definition.

## How You Operate

You drive the pipeline by invoking the existing `/workflows:*` sub-commands in order. Each sub-command has its own internal questions. Your role is to **filter those questions**:

- **Menial prompts** (branch naming, "proceed?", detail level, "continue on this branch?") → answer them yourself with the sensible default below. Do **not** forward them to the user.
- **Judgment prompts** (which approach to build, approval to start implementing, which findings to fix) → in **`--steer`/`--careful`**, surface them via **AskUserQuestion**. In the **autonomous modes** (default and `--final-review`), answer them yourself per the Decision Policy and record the call in the decision log — only a genuine blocker goes to the user.

You also **insert your own gates** where the pipeline itself wouldn't stop: the Plan-Approval gate (steer/careful) and the Final-Review gate (`--final-review` only — the default merges without it).

**Between checkpoints, do not stop.** Proceed from stage to stage automatically, emitting a one-line status banner at each transition so the user can watch progress. Only an AskUserQuestion checkpoint or a blocker pauses you.

### Delegation & Review (autonomous modes)

The orchestrator does not implement feature code inline. It sits at the top of a two-tier structure:

- **Orchestrator (this session — the strongest model available).** Owns the pipeline state machine, the tracker, all judgment calls, and **review of everything a sub-agent returns**. Reviewing is the orchestrator's real job: read the returned diff against the acceptance criteria, re-run the project's quality gates at the top level, and reject work that doesn't hold up.
- **Implementation sub-agents.** Each tracked issue / plan task is dispatched to one focused sub-agent via the Agent tool, using the **Orchestrated Execution** engine in `/workflows:work` (its subagent brief, wave planning, and terminal-state rules apply verbatim). Run implementation sub-agents on an Opus-tier model (`model: "opus"`) in the background; reserve the orchestrator's own tier for review and steering, and drop to a cheaper tier for purely mechanical chores (docs regeneration, count bumps). Dispatch file-disjoint work in parallel (worktree-isolated when agents would touch the same repo); serialize the rest.

The review loop per returned sub-agent: **verify → accept, retry, or escalate.** Criteria met and gates green → accept and advance the tracker. Gates fail or criteria unmet → re-dispatch with the specific failure appended, max ~2 retries. Still failing, or the failure needs a human decision → blocker. Never accept unreviewed work, and never let a sub-agent's "done" substitute for your own verification. Both tiers run on the `operating-principles` skill: sub-agents load it via the brief template, and the orchestrator applies its independent-channel verification and Verified / Checked / Assumed calibration when judging returned work — a sub-agent's *checked* is not the orchestrator's *verified*.

**Decision log.** Every judgment call you make on the user's behalf (approach picked, plan self-approved, findings triaged, retries burned, scope filed as follow-ons) gets one line: `↳ decided: <what> — <why, briefly>`. Emit it in the status stream as it happens and replay the full log at the Final-Review gate / final summary. This is what makes autonomous continuation reviewable after the fact.

## Decision Policy

This table is the heart of the orchestrator. Apply it literally. **🧍 CHECKPOINT** rows pause for the user in `--steer`/`--careful`; in the **autonomous modes** (default and `--final-review`) they collapse to the *Autonomous self-answer* noted in the row (logged in the decision log), with two exceptions that always hold: genuine blockers escalate, and material scope expansion stops the run. The **merge** row is the one place the two autonomous modes differ: the default merges once landable, and `--final-review` pauses there at the Final-Review gate.

| Juncture | Mode | Default action |
|----------|------|----------------|
| Run repo preflight, print tracker banner | **AUTO** | Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/workflow-repo-preflight.py"`; follow its `recommendation.action`. |
| Brainstorm: lightweight repo research | **AUTO** | Let it run. |
| Brainstorm: **which approach to build** | **🧍 CHECKPOINT** | The user picks — this is WHAT-we-build steering. *Autonomous self-answer:* pick the approach the brainstorm's own analysis recommends and log it; if the fork is product-shaping with no clear winner, that's a blocker — escalate, don't guess. |
| Brainstorm → plan transition | **AUTO** | When the brainstorm doc is written and its open questions are resolved, proceed to `/workflows:plan` (it auto-detects the brainstorm). |
| Plan: research depth decision | **AUTO** | Let `/workflows:plan` decide per its own rules; don't intervene. |
| Plan: detail level (MINIMAL/MORE/A LOT) | **AUTO** | Choose by scope: bug/small → MINIMAL, typical feature → MORE, architectural/multi-phase → A LOT. |
| Plan: tracker-issue creation | **AUTO** | Mandatory Step 7 runs as-is: it creates/updates the GitHub issue, sub-issues (via the plan), dependencies, board-adds, and sets Status=`planned`. Capture the issue number `#<N>`. |
| **Plan-Approval gate** (plan written, before any code) | **🧍 CHECKPOINT** | Show a tight plan summary + issue number `#<N>`. Ask: proceed / deepen first / refine / edit-and-recheck. See gate spec below. *Autonomous self-answer:* run the **plan self-review** (the `document-review` skill, plus `spec-flow-analyzer` for user-facing flows), fix what it surfaces, log the approval, and proceed — the plan summary is replayed at the Final-Review gate. |
| Deepen the plan | **🧍 CHECKPOINT** (folded into Plan-Approval) | Only run `/deepen-plan` if the user asks for it at the gate, or (autonomous) the plan is large/architectural. |
| Work: branch / worktree setup | **AUTO** | If already on a feature branch, continue on it. Else create `feat/…`-style branch from the default branch. Never commit to the default branch without explicit user say-so (that itself becomes a blocker → ask). |
| Work: clarifying questions about the plan | **AUTO if resolvable** | Resolve from the plan + repo. Only escalate genuinely ambiguous items as a blocker. |
| Work: implementation, tests, incremental commits | **AUTO** | In the autonomous modes: dispatch via **Orchestrated Execution** (see Delegation & Review) — one Opus-tier sub-agent per tracked issue/sub-issue; `/workflows:work` claims each via `--claim` (assignee = claim) and advances Status through `--set-status`. The orchestrator reviews every returned diff and re-runs gates before accepting. In `--steer`/`--careful`: execute per `/workflows:work` (inline is fine for small linear work). |
| Work: discovered scope expansion | **🧍 CHECKPOINT if material** | A small follow-on task → file it and proceed (all modes). A direction change or significant new scope → pause and ask — **in every mode, including the fully-autonomous default**; redefining WHAT is being built is always the user's call, and counts as a genuine blocker. |
| Work: open the PR | **AUTO** | `/workflows:work` Phase 4 opens the PR with `Closes #N` and sets Status=`in_review` (the issue is **not** closed at PR creation — the built-in "Item closed" automation owns `shipped` at merge). Outward-facing, but it's the expected terminal of the work stage in a solo/small-team flow. |
| Review: run multi-agent review | **AUTO — mandatory, never skipped in any mode (the fully-autonomous default included)** | Run `/workflows:review` against the new PR. This is the **independent** review that justifies the eventual merge: it fans out to fresh reviewer sub-agents (not the implementer), and `/workflows:review` always runs a baseline set (`agent-native-reviewer`, `learnings-researcher`, `integration-boundary-reviewer`) even with no `review_agents` configured — so the review is never empty. In the autonomous modes, if no `agentic-engineering.local.md` exists, proceed with that baseline rather than blocking on the interactive `setup` skill. A run that reaches land/merge without this review having run this cycle has no basis to merge — `land-pr` re-checks and runs it if it is somehow missing (condition 3). |
| Review: **P1 (critical) findings** | **AUTO-FIX** | P1 blocks merge — fix it without asking (via `/resolve_todo_parallel` or direct edits), then re-verify. |
| Review: **P2 / P3 findings triage** | **🧍 CHECKPOINT** | Present the categorized findings. The user decides which non-blocking items to fix now vs defer. *Autonomous self-answer:* fix P2s now, defer P3s as tracked todos/beads, log the split — the triage is replayed at the Final-Review gate. |
| Review: resolve approved findings | **AUTO** | Run `/agentic-engineering:resolve_todo_parallel` to fix the items the user approved (and all P1s). |
| Verify: browser / E2E tests (`/agentic-engineering:test-browser`) | **AUTO when applicable** | After findings are resolved, for web/iOS changes run `/test-browser` on affected pages. Failures become P1 todos → fix and re-run until green. Skip for non-UI changes (note the skip). |
| Finalize: feature walkthrough video (`/agentic-engineering:feature-video`) | **AUTO when applicable** | For UI / user-facing changes, record the walkthrough and attach it to the PR (`/feature-video`). Skip with a one-line note for internal-only changes, or if the user opted out at the triage gate. |
| Land: drive CI green + resolve threads (`land-pr` skill) | **AUTO** | Run the `land-pr` skill to wait on CI, resolve any remaining review threads, and reach a landable state (CI green, threads resolved, mergeable). The independent review that justifies the merge already ran upstream (the Review stage above) — that, not a human GitHub approval, is the review gate. |
| Land: **the merge itself** (`gh pr merge`) | **AUTO** (default) / **🧍 FINAL-REVIEW GATE** (`--final-review`) / **🧍 CHECKPOINT** (steer/careful) | Merging is outward-facing and irreversible. In the **default** (fully autonomous) mode, the `land-pr` skill merges with no prompt — **once** CI is green, the upstream multi-agent review ran with P1s resolved, all threads are resolved, and the PR is mergeable. Under **`--final-review`**, this is the run's single surfacing point: present the **Final-Review packet** (see gate spec below) and wait for the user's go. In **`--steer`/`--careful`**, stop and ask before merging. In all cases, do **not** wait on a human GitHub `APPROVED` (a solo run never gets one — that's the whole point of the autonomous review). Never merge on an unmet condition or directly to the default branch. The one real stop even in the default is `mergeStateStatus: BLOCKED` (branch protection requires something the agent can't supply) → escalate as a blocker. |
| Compound: document the solution | **AUTO** | Run `/workflows:compound` once work has shipped (merged) and a non-trivial problem was solved. |
| Compound: ship the knowledge PR (`land-docs` skill) | **AUTO** | Compound's Phase 3 spins the written markdown off into its own **docs-only** PR via the `land-docs` skill, **submitted with GitHub auto-merge armed at creation** so it lands on green with no separate user turn (even if the session has ended). `land-docs` enforces a docs-only scope gate (any non-doc path aborts before the PR opens → blocker) and follows CI: pass → GitHub auto-merges; simple failure → fix; failure needing input → escalate. This is the seam that used to bounce back to the user after the code PR merged. |
| Any genuine blocker | **🧍 ESCALATE** | Access, credentials, an ambiguous product decision, conflicting requirements, a failing gate you can't resolve in ~2 tries. Batch open blockers into ONE AskUserQuestion. Never guess on irreversible or product-shaping choices. |

Mode collapse rules, precisely: in the **default** (fully autonomous) mode, every **🧍 CHECKPOINT** collapses to its *Autonomous self-answer*, leaving **material scope expansion and genuine blockers as the only stops** — the run merges once landable with no other pause. That pair is the universal floor: it surfaces in *every* mode — autonomy never extends to redefining WHAT is built or overriding a blocker. **`--final-review`** is the default plus exactly one reinstated stop: the Final-Review gate at the merge (the packet is presented and the run waits for the user's go). In `--careful`, add a lightweight confirm at each stage boundary on top of the steer checkpoints.

## State Detection (Resumable)

Re-running `/workflows:orchestrate` should pick up where things left off. The board is the source of truth for pipeline stage — orchestrate reads it via `lifecycle_board.py` verbs, never by inferring stage from filenames or recency.

### Entry sequence (every run, and after each stage)

1. **Reconcile first.** Run:

   ```
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/lifecycle_board.py" --reconcile
   ```

   This is TTL-cached (a warm entry is a no-op) and repairs drift so the stage you read next is trustworthy. It emits a `flags` array — **surface these in the status stream**:
   - `merged_to_non_default_branch` → **blocker**: the PR merged onto a non-default branch so GitHub won't auto-close the issue and it stalls at `in_review`. Escalate with the reconciler's fix (the issue-closer workflow, or a manual close). Do not treat the item as shipped.
   - `stale_join_key` → **blocker/note**: the doc's `github_issue` no longer resolves. Stop acting on that issue; surface the note so the user can fix the frontmatter.
   - `truncated_ready_work` → **note**: only relevant to `--ready-work` (below); mention that Priority ordering may be incomplete.

2. **Resolve the issue number.** The join key is the identity:
   - The **input arg** (a `#N`, or a brainstorm/plan path whose frontmatter carries `github_issue: N`), else
   - the `github_issue:` frontmatter of the brainstorm/plan this run is resuming.

3. **Gate on the known issue.** When an issue number is known, run:

   ```
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/lifecycle_board.py" --gate orchestrate --issue <N>
   ```

   It returns `{mode, verdict, stage, plan_doc, brainstorm_doc, flags, …}`. Orchestrate consumes the **raw `stage`** (the gate's verdict for `orchestrate` is always `proceed` — orchestrate applies its own ladder below) plus `plan_doc`/`brainstorm_doc` as the join-keyed artifacts. If `mode` is `no_board` (or the gate returns `verdict: no_board`), fall through to **Legacy fallback**.

### Stage → resume point

Map the board `stage` to a resume point (this replaces the artifact-heuristic ladder):

| Board `stage` | Resume at |
|---|---|
| `stub` | **brainstorm** |
| `brainstormed` | **plan** |
| `planned` | **work** (fresh — Plan-Approval gate in steer/careful, or plan self-review when autonomous, if neither has happened this run) |
| `in_progress` | **work** (resume — claim already held) |
| `in_review` | the **review → land** ladder — sub-detect within `in_review` from the PR (see below) |
| `shipped` | **compound** |
| `deployed` | **compound** (deployed is a terminal refinement of shipped; compound resumes from `shipped` **or** `deployed`) |
| `compounded` | pipeline **complete** — report and stop |
| `abandoned` | report the item is abandoned and **stop** (no further pipeline runs on it) |

**Segment bounds (when a segment flag is set).** Under `--groom`, the ladder is truncated at grooming: `stub`/`brainstormed` resume as shown, and `planned` (with its plan doc) or any later stage reports already-groomed / past-grooming and **stops** — the groomed packet replaces the final summary. Under `--implement`, it is truncated from below: `stub`/`brainstormed` — or `planned` whose plan doc is missing — **stop and route to `/workflows:groom`**; `planned` and later resume as shown.

**`in_review` sub-detection (PR-based, unchanged).** Once the board says `in_review`, the finer position within review → land is still read from the PR — keep the existing gh-based checks (use explicit `--repo`/`--owner` on every invocation):

- `gh pr view --repo <owner>/<repo> …` reports **MERGED**, stage not yet advanced → the merge automation is mid-flight; the reconciler in step 1 stamps `shipped` — re-read and resume at **compound**.
- Open PR, findings resolved, video done (or N/A), not yet merged → resume at **land-pr** (drive CI green → merge gate → merge), then **compound**.
- Open PR, findings resolved, no walkthrough video in the PR body (and the change is UI/user-facing) → resume at **feature-video**, then **land-pr**.
- Open PR + un-triaged findings (`todos/*-pending-*.md`) → resume at **findings triage** → resolve → **test-browser** → **feature-video** → **land-pr**.
- Open PR, no review yet → resume at **review**.

### No known issue → ready-work

With no issue number resolvable (empty input, or a bare feature description):

- Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/lifecycle_board.py" --ready-work` — it returns dispatchable items (`planned ∧ unassigned ∧ unblocked`, **Priority-sorted**). **Offer the top item** (when autonomous, take it and log the pick; in steer/careful, confirm via AskUserQuestion). A `truncated_ready_work` flag means the list may be incomplete — note it.
- If the input is instead a **feature description**, don't consult ready-work — start a new run at **brainstorm** (or skip to **plan** if the description is already crisp and well-scoped: clear acceptance criteria, referenced patterns — say so).
- If `--ready-work` returns no items and there's no description, ask the user once what to build.

### Legacy fallback (no board / un-keyed docs)

Used **only** when `--gate` reports `mode: no_board` / `verdict: no_board` (plain `github` or `none` mode — no committed board config) **or** no `github_issue` join key exists for the artifact being resumed. In that case the board can't tell us the stage, so fall back to the old artifact-existence ladder (most-advanced signal wins):

1. **Solution doc** for this feature exists in `docs/solutions/` → pipeline **complete**. Report and stop.
2. **PR merged** (`gh pr view` reports `MERGED`), no solution doc yet → resume at **compound** (or done).
3. **Open PR**, findings resolved, video done (or N/A), **not yet merged** → resume at **land-pr** (drive CI green → merge gate → merge), then **compound**.
4. **Open PR**, findings resolved, but **no walkthrough video** in the PR body (and the change is UI/user-facing) → resume at **feature-video**, then **land-pr**, then **compound**.
5. **Open PR** + un-triaged findings (`todos/*-pending-*.md`) → resume at **findings triage** → resolve → **test-browser** → **feature-video** → **land-pr**.
6. **Open PR**, no review yet → resume at **review**.
7. **Plan** exists (`docs/plans/<recent>-plan.md`), checkboxes unstarted/partial, branch may exist → resume at **work** (after the Plan-Approval gate in steer/careful, or the plan self-review when autonomous, if neither has happened this run).
8. **Brainstorm** exists (`docs/brainstorms/<recent>.md`), no matching plan → resume at **plan**.
9. **Nothing in flight** → start at **brainstorm**, unless the input description is already crisp and well-scoped (clear acceptance criteria, referenced patterns), in which case skip straight to **plan** and say so.

"Recent / matching" (legacy fallback only) = filename or frontmatter topic semantically matches the feature, created within ~14 days; if several match, use the most recent (or ask in `--careful`). Reuse the matching logic the sub-commands already apply.

## The Main Loop

```
resolve autonomy mode + segment + input
run repo preflight (AUTO) → print tracker banner
detect current stage (State Detection; apply segment bounds)

loop until pipeline complete (or the segment's terminal stage is reached):
    emit status banner: "▶ Stage: <name> — <one line of what's happening>"
    run the stage's sub-command, applying the Decision Policy:
        - auto-answer menial prompts with the documented defaults
        - judgment prompts: AskUserQuestion in steer/careful;
          self-answer + decision log when autonomous (default / --final-review)
        - work stage when autonomous: dispatch sub-agents per
          Delegation & Review; verify every returned diff before accepting
        - honor the inserted gates (Plan-Approval in steer/careful;
          Final-Review under --final-review only — the default merges without it)
    on stage completion:
        - update trackers / check off plan checkboxes (AUTO, handled by sub-commands)
        - re-detect stage; reset the stall counter (progress was made)
    on no progress this pass (see No-Progress Stop):
        - increment the stall counter for the current stage
        - if the counter reaches 2, enter the `stalled` terminal state for this
          stage → escalate as a blocker with the specific evidence
    on blocker:
        - collect it; if more of the current stage can proceed without it, continue
        - otherwise batch all open blockers into ONE AskUserQuestion and wait
        - on answer: resume (reset the stall counter — new information arrived)

on completion: emit final summary (below)
```

Never report "done" while a stage is half-finished, a P1 finding is open, a blocker is unanswered, or a stage is `stalled`.

## No-Progress Stop (uniform)

A single stagnation rule governs the whole run, so no stage can spin forever and every stage inherits the same bound instead of re-inventing "try a couple of times." This replaces per-stage retry prose with one mechanism.

**Progress metric (evaluated once per pass).** A pass **made progress** iff the board `stage` advanced **or** at least one of these strictly decreased versus the previous pass at this stage:

- open sub-issues on the parent,
- unresolved review threads on the PR,
- failing required CI checks,
- open P1 findings.

Anything else — same counts, a re-run that changed nothing, a fix that didn't move any of the four — is a **no-progress pass**. The metric is evidence-based on purpose: it is not a clock, an iteration cap, a token budget, or a retry ceiling invented out of nothing. A genuinely advancing long run never trips it; only a spinning one does.

**Stall counter.** One counter per stage. Increment it on each no-progress pass; **reset it to 0** on any progress or stage advance, and whenever a blocker answer injects new information.

**Stop at 2.** Two consecutive no-progress passes at the same stage → that stage enters the **`stalled`** terminal state. Stop working it, gather the evidence (what was attempted on both passes, which of the four metrics did not move, the exact failure), and escalate as a blocker in the normal one-batch AskUserQuestion. `stalled` is a terminal state distinct from success — **never report a stalled stage as done**, and never auto-merge out of one.

**Where the existing "~2 retries" live.** The bounded retries inside `land-pr` (drive-to-green) and `/workflows:work` Orchestrated Execution are *instances* of this rule: a retry that does not strictly shrink the blocker/failure set counts toward the stall bound. Treat their local counters and this run-level counter as the same budget — two dry attempts, then escalate.

## Checkpoint Specs

### Approach selection (during brainstorm)

In `--steer`/`--careful`: let `/workflows:brainstorm` run its own approach exploration and AskUserQuestion — that question is already a meaningful one. Do not pre-answer it. When autonomous (default / `--final-review`): intercept it, pick the recommended approach, log the decision (escalating only a product-shaping fork with no clear winner). Once the approach is settled and the brainstorm doc is written with open questions resolved, proceed automatically to plan.

### Plan-Approval gate (steer/careful — replaced by plan self-review when autonomous)

After the plan file is written and its tracker issue is created, **stop**. Show:

```
✅ Plan ready — <plan_path>  (tracked as #<github_issue>)

What it builds:  <2–3 line summary>
Approach:        <1 line>
Scope:           <key acceptance criteria, bulleted, max 5>
Risk notes:      <anything notable: migrations, external wiring, security>
```

Then **AskUserQuestion**: *"Plan is ready. How should I proceed?"*

- **Proceed to work** — start implementing now (the common path).
- **Deepen first** — run `/deepen-plan`, then return to this gate.
- **Refine** — structured self-review via the `document-review` skill, then return here.
- **Let me edit** — open the plan (`open <plan_path>`), wait for the user, then re-read and return here.

This gate is the single point where the user commits to an implementation before code is written. It applies in `--steer` and `--careful`. In the **autonomous modes** (default and `--final-review`), the same commitment is made by the **plan self-review** instead: run the `document-review` skill against the plan (plus `spec-flow-analyzer` when the change has user-facing flows), fix what they surface, log `↳ decided: plan self-approved — <one-line basis>`, and proceed to work. The plan summary block above is still produced — under `--final-review` it opens the Final-Review packet; in the default it opens the final summary.

### Findings triage (after review)

P1 findings are already auto-fixed before you reach this gate. When autonomous (default / `--final-review`): fix P2s, defer P3s as tracked todos/beads, log the split, and move on — no pause. In `--steer`/`--careful`, present the rest:

```
🔍 Review complete — PR #<n>
  🔴 P1: <count>  (fixed automatically)
  🟡 P2: <count>
  🔵 P3: <count>
```

Then **AskUserQuestion**: *"P1s are fixed. Which non-blocking findings should I address now?"*

- **Fix P2s now** — resolve important findings, defer nice-to-haves.
- **Fix everything** — resolve P2 + P3 via `/resolve_todo_parallel`.
- **Defer all** — leave P2/P3 as tracked todos/beads for later.
- **Let me pick** — show the list; the user selects specific items.

After resolution, proceed to compound (AUTO).

### Final-Review gate (`--final-review` only)

This gate exists **only under `--final-review`.** The default (fully autonomous) mode has no such gate — it merges once the PR is landable and emits the packet below as its final summary instead of a question. Under `--final-review`, it is reached when `land-pr` reports the PR **landable**: CI green, review threads resolved, P1s (and P2s, per the triage rule) fixed, mergeable. Present the **Final-Review packet**:

```
🏁 Ready to land — PR #<n> (<url>)

  Built:        <2–3 line summary of what shipped and why>
  Plan:         docs/plans/<file>  (#<N>)
  Review:       <P1 fixed> / <P2 fixed> / <P3 deferred: list>
  Verify:       tests ✓ · lint ✓ · test-browser <pass/N-A> · video <link/N-A>
  Sub-agents:   <count> dispatched, <count> retried, <count> escalated

  Decisions made on your behalf:
    ↳ <replay the decision log, one line each>
```

Then **AskUserQuestion**: *"Everything is green and reviewed. How should I land it?"*

- **Merge now** — squash-merge via `land-pr`, then proceed to compound.
- **I'll review first** — pause; on resume, re-verify landability and return here.
- **Request changes** — take the user's feedback as new P1 todos, resolve, and return here.
- **Don't merge** — leave the PR open, note why, and stop after emitting the final summary.

This gate is the whole of what `--final-review` adds over the default — one pause, at the merge, and nothing else. The default omits it and merges automatically once landable, emitting the same packet as its final summary. Either way every other stop is unaffected: material scope changes and genuine blockers still surface, in every mode.

## Sub-command Auto-Answer Cheatsheet

When a sub-command asks one of its built-in questions, answer as the orchestrator (don't forward) unless the Decision Policy marks it 🧍:

| Sub-command prompt | Orchestrator's auto-answer |
|--------------------|----------------------------|
| brainstorm: *"requirements look clear — plan directly?"* | If input was crisp → yes, go to plan. Else continue brainstorming. |
| brainstorm Phase 4: *"what next?"* | **Proceed to planning.** |
| plan: *"description clear — proceed with research?"* | **Proceed.** |
| plan: detail level | Pick by scope (see Decision Policy). |
| plan Post-Generation menu | Route to the **Plan-Approval gate** (steer/careful) or the **plan self-review** (autonomous) instead of auto-picking. |
| deepen-plan Post-Enhancement menu | **Start `/workflows:work`** (you only got here if the user chose to deepen). |
| work Phase 1: *"continue on branch X or new branch?"* | Continue if on a feature branch; else new `feat/…` branch. |
| work: *"commit to default branch?"* | **Never auto-yes.** Escalate as a blocker. |
| review: inline end-to-end testing offer | **Decline** — the dedicated `test-browser` finalization stage handles E2E so it isn't run twice. |
| test-browser: human-verification pauses (OAuth/email/payment/IAP) | **Forward to user** — these are genuine manual-verification steps, not menial. |
| feature-video: *"record a walkthrough?"* | Run it for UI/user-facing changes; skip (noted) for internal-only changes. |
| compound: *"what's next?"* | **Suppressed** — the compound stage routes to the `land-docs` skill (docs-only PR → merge on green) instead of the blocking menu. Don't forward it. |
| any `--gate` verdict | **Auto-follow it.** `proceed` → run the stage. `already_done` → skip the stage (it's complete on the board). `route_to_plan` → run `/workflows:plan`. `route_to_work` → run `/workflows:work`. `repair_needed` → the reconciler already handled it — re-read stage and continue. `no_board` → fall to Legacy fallback. |
| `--claim` returns `claim_conflict` | **Blocker.** Another agent/human owns the issue (or is racing for it). Do not force the claim — escalate. |
| `--reconcile`/`--gate` `flags` present | **Surface in the status stream** — `merged_to_non_default_branch` and `stale_join_key` as blockers/notes (see State Detection step 1); `truncated_ready_work` as a note. |

When you auto-answer, briefly note it in the status banner (e.g., `↳ auto: detail level = MORE`) so the user can see the decisions you're making on their behalf.

## Final Summary

When the pipeline completes, emit:

```
🎉 Pipeline complete — <feature>

  Brainstorm  ✓  docs/brainstorms/<file>
  Plan        ✓  docs/plans/<file>   (#<N>)
  Work        ✓  PR #<n> — <url>
  Review      ✓  <P1 fixed> / <P2 handled> / <P3 deferred>
  Verify      ✓  test-browser: <pass/fail/N-A>
  Video       ✓  walkthrough attached to PR  (or: N/A — internal change)
  Land        ✓  PR #<n> merged (squash, branch deleted)
                 (--final-review: ⏸ paused at Final-Review gate — your call)
                 (steer mode: ⏸ paused at merge gate — your call)
                 (blocked: 🚧 branch protection needs <reason> you must supply)
  Compound    ✓  docs/solutions/<file>  →  docs PR #<d> merged (docs-only, auto)
                 (paused: ⏸ a docs-PR check needs your input — <reason>)

  Sub-agents:            <count> dispatched / <count> retried / <count> escalated
  Decisions you made:    <count>  (approach, plan-approval, triage, merge, …)
  Decisions I auto-made: <count>  (decision log replayed above / at the gate)
  Deferred for later:    <list of deferred todos/beads, if any>

Next: <if merged> done — PR #<n> is in <default-branch>.  <if --final-review or steer-mode paused> the PR is green and reviewed — approve the merge to land it.  <if blocked> branch protection requires <reason>; supply it, then the merge lands.
```

## Guardrails

- **Don't suppress meaningful questions.** In `--steer`/`--careful`, when in doubt about whether a juncture is menial or meaningful, treat it as meaningful and ask. When autonomous (default / `--final-review`), the same doubt resolves differently: if the call is recoverable and reviewable from the decision log, decide it yourself and log it; if it is product-shaping, irreversible, or would be expensive to unwind, it's a blocker — ask. Autonomy is never a license to guess on the calls that matter.
- **Don't ask about chores.** Branch names, "should I proceed", detail levels, tracker bookkeeping — decide and move.
- **Autonomous runs are still reviewed.** Autonomous continuation rests on two reviews the orchestrator itself performs: the per-sub-agent diff review (nothing is accepted unverified) and the independent multi-agent `/workflows:review` of the PR. If either is skipped, the run has no basis to reach a merge — whether that merge is gated by `--final-review` or automatic in the default.
- **Irreversible / outward-facing actions** beyond the expected pipeline (force-push, closing others' PRs, deleting unrelated branches, anything touching the default branch directly) → always a blocker, never auto. The exceptions are the pipeline's own expected outward steps: opening the PR (`/workflows:work` Phase 4) and, **in the default (fully autonomous) mode**, the `land-pr` merge — which squash-merges and deletes *its own just-merged feature branch* only after CI is green, the upstream independent review ran with P1s resolved, threads are resolved, and the PR is mergeable. (This is not a human-approval wait — see the Land rows above. Under `--final-review`, and in `--steer`/`--careful`, the merge additionally waits on a gate.)
- **Honor every sub-command's own gates** — the tracker-issue gate in `/workflows:plan`, the P1-blocks-merge rule in `/workflows:review`, and the entry gates + writer contracts in every command (one writer per transition; the reconciler's closed repair set). You orchestrate them; you don't override them.
- **Never bypass a verb.** Orchestrate reads board state through `--gate`/`--ready-work` and moves it through the sub-commands' own `--claim`/`--set-status` writers — never a raw `gh project item-edit`, raw item mutation, or hand-assembled board write of its own.
- **Segment bounds are hard.** Under `--groom`, reaching `planned` ends the run — the groomed packet is the final output; never roll into work "to be helpful." Under `--implement`, an un-groomed item is a routing stop (→ `/workflows:groom`), never an invitation to groom inline.
- **Stay resumable.** Drive state from artifacts, not memory. If interrupted, a fresh `/workflows:orchestrate` must be able to pick up exactly where this left off.
- **One blocker batch at a time.** Don't drip-feed questions. Collect everything that needs the user, ask once, then run.
