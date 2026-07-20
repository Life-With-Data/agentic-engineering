# Work Plan Execution

Execute a work plan efficiently while maintaining quality and finishing features.

## Introduction

This route takes a work document (plan, specification, or tracked task) and
executes it systematically. The focus is on **shipping complete features** by
understanding requirements quickly, following existing patterns, and
maintaining quality throughout.

## Input Document

<input_document> #$ARGUMENTS </input_document>

## Entry Gate

**Writer contract.** This route performs **exactly two parent-stage transitions** and no others:

- `planned → in_progress` — the claim (Phase 1, via `--claim`).
- `in_progress → in_review` — PR open (Phase 4, via `--set-status <N> in_review`).

It never writes any other parent stage, never closes the parent issue, and never hand-assembles board GraphQL. The built-in "Item closed" automation owns `→ shipped` when the merge closes the issue; the shared reconciler owns every repair. Separately, it drives its **sub-issues'** `status:*` labels via `--sub-status` (in_progress/in_review/blocked/done) — a PR-less, board-free track defined by the `wf-setup` lifecycle route; only the owning agent writes it, never a dispatched sub-agent. Sub-issues are the task tracker; an in-session task list is disposable scratch state.

**Stage semantics.** Use the `wf-setup` lifecycle route for the 9-stage enum,
writer table, and entry-gate/verdict vocabulary, then return here.

**Execution discipline.** Decompose work by risk and dependency, define an exit
check for every subtask, and verify results through a channel independent of the
one that produced them. The phases below define sequencing; repository capability
targets define the commands and evidence available in the current repository.

**Resolve the issue number `<N>`.** Take `<N>` from an explicit issue-number argument if one was given; otherwise read the `github_issue:` frontmatter key from the input plan document. If neither yields a number, there is no board item to gate on — proceed as the `no_board` branch (legacy flow) below.

### Preflight, banner, reconcile — then the gate

Run these in order, once, at entry:

1. **Preflight (read-only).** Use its JSON output as the source of truth for branch/dirty/PR state and tracker resolution. It never mutates.

   ```bash
   python3 "<skill-directory>/scripts/workflow-repo-preflight.py"
   ```

   Relevant fields:
   - `repo.current_branch`, `repo.default_branch`, `repo.working_tree_dirty`
   - `github.current_branch_pr` (if `gh` is installed/authenticated)
   - `integrations.issue_tracker_resolved` — one of `github-project | github | none`
   - `integrations.issue_tracker_source`
   - `recommendation.action` and `recommendation.prompt`

   Print a one-line tracker banner before continuing:
   ```
   Tracker: <issue_tracker_resolved> (<issue_tracker_source>)
   ```

   Follow `recommendation.action` rather than re-deriving branch state by hand.

2. **Reconcile once (TTL-cached).** Repair any drift on the board's active items before gating, so the gate reads settled state. This is a no-op within the session TTL and degrades to reported JSON on partial failure — never fail the command on it.

   ```bash
   python3 "<skill-directory>/scripts/lifecycle_board.py" --reconcile
   ```

3. **Gate.** Invoke the gate for this command with the resolved issue number:

   ```bash
   python3 "<skill-directory>/scripts/lifecycle_board.py" --gate work --issue <N>
   ```

   The gate returns `{mode, verdict, route, reason, stage, issue, plan_doc, flags, ...}`. Branch on the **closed** `verdict` enum — never re-derive stage from prose or filenames:

   | `verdict` | What it means | Action |
   |-----------|---------------|--------|
   | `proceed` | `stage ≥ planned` **and** a join-keyed plan doc exists | Continue to **Phase 1**. |
   | `route_to_plan` | Not yet groomed to `planned`, **or** Status says planned but no plan doc | Tell the user to run **the `wf-grooming` planning route** first. Hotfixes bypass the board entirely (plain PR flow, no gate, no board exception). **STOP.** |
   | `already_done` | Stage is terminal (`shipped`/`deployed`/`compounded`) or `abandoned` | Report the stage to the user and that the work is already at/past this command's scope. **STOP.** |
   | `repair_needed` | Stale join key, or a stage claiming `planned`/`brainstormed` with no matching artifact | The board can't be trusted for this item. Report the flag/reason, tell the user to fix the doc's `github_issue:` frontmatter (or re-run the `wf-grooming` planning route if the plan doc is genuinely missing), and **STOP**. |
   | `no_board` | No board configured (mode is `github`/`none`) | Fall through to the **Legacy flow (no board)** below and continue **degraded** — no stage machinery, no board writes. |

   `claim_conflict` and `blocked` are **not** gate verdicts — they are returned by `--claim` in Phase 1, not here. Only `proceed` (with a board) and `no_board` (degraded) continue past this gate; every other verdict **STOPs**.

### Legacy flow (no board)

When `verdict == no_board`, the repo has no configured Projects board. Behave as the plugin did before the lifecycle: drive the work with **TodoWrite** as the task list, use plain `gh issue`/`gh pr` in `github` mode (or nothing in `none` mode), and skip every `--claim`/`--set-status`/`--ready-work`/sub-issue step below. The Phases still apply structurally; substitute TodoWrite for the board wherever a stage transition or sub-issue action is named, and open the PR normally in Phase 4 without a board write.

## Execution Workflow

### Phase 1: Claim & Setup

1. **Read Plan and Clarify**

   - Read the work document completely.
   - Review any references or links provided in the plan.
   - If anything is unclear or ambiguous, ask clarifying questions now and get user approval to proceed.
   - **Do not skip this** — better to ask now than build the wrong thing.

2. **Claim the work item** (board mode)

   The claim is a single verb. Do **not** hand-roll assignment, sole-assignee confirmation, blocked-by checks, or the `in_progress` write — `--claim` does all of it atomically-in-order (assign → re-read → confirm sole assignee → verify `blocked-by` empty → Status = `in_progress`):

   ```bash
   python3 "<skill-directory>/scripts/lifecycle_board.py" --claim <N>
   ```

   Branch on the returned `verdict`:
   - `proceed` — you now hold the claim (Status is `in_progress`). Continue.
   - `claim_conflict` — another assignee holds it (or a race left multiple assignees and you yielded). Report the holder from `reason` and **STOP**.
   - `blocked` — the issue has open blocking issues. Report them and **STOP**; dependencies are advisory but a blocked item is not ready to work.

   In the **legacy flow**, skip this step — TodoWrite is your tracker and there is no assignment to claim.

3. **Setup Environment**

   Use the preflight JSON (from the Entry Gate) for branch state.

   **If already on a feature branch** (not the default branch):
   - Ask: "Continue working on `[current_branch]`, or create a new branch?"
   - If continuing, proceed to Phase 2.

   **If on the default branch**, choose how to proceed:

   **Option A: Create a new branch** — name it `feat/<N>-<slug>` (the issue number is a **secondary claim signal**: it lets humans and the duplicate-PR check tie a branch back to the claimed issue). Slugify the title to `[a-z0-9-]` first.
   ```bash
   git pull origin [default_branch]
   git checkout -b feat/<N>-<slug>
   ```

   **Option B: Use a worktree (recommended for parallel development)**
   ```bash
   bash <skill-directory>/scripts/worktree-manager.sh create <branch-name>
   ```
   Name the branch `feat/<N>-<slug>` here too.

   **Option C: Continue on the default branch** — requires explicit user confirmation. Never commit directly to the default branch without an explicit "yes, commit to [default_branch]".

   **Recommendation:** use a worktree when working on multiple features simultaneously, keeping the default branch clean, or switching branches frequently.

4. **Decompose into tasks (sub-issues)**

   the `wf-grooming` planning route already created the sub-issues that decompose this work item — you do **not** create them here. List them:

   ```bash
   # Sub-issues of the claimed parent <N>:
   gh issue view <N> --repo <origin> --json subIssues
   # Or across the repo, resolving parents:
   gh issue list --repo <origin> --json number,title,parent
   ```

   (`<origin>` is `owner/repo` from the origin remote — every `gh` write in this command carries an explicit `--repo`/`--owner`.)

   The open sub-issues are the authoritative task list. **TodoWrite** remains the implementer's in-session scratchpad for finer-grained steps — non-authoritative and disposable. (Beads is opt-in for long-running personal notes only: never a gate input, never synced, never a lifecycle writer.)

### Phase 2: Execute

**Choose your execution model first:**

| Model | Use when | How it runs |
|-------|----------|-------------|
| **Inline** (default, below) | A plan/spec you implement yourself; simple, linear work | You implement each sub-issue directly in this session, closing each as its criteria pass. |
| **Orchestrated** ([section](#orchestrated-execution-board-driven)) | Work backed by tracked sub-issues — one or many | You own the board/sub-issue state and drive one subagent per sub-issue, looping each to a terminal state before returning. |
| **Swarm** ([section](#swarm-mode-optional)) | 5+ independent workstreams needing maximum parallelism | Long-lived teammates self-claim from a shared queue. |

Even a **single** tracked item benefits from Orchestrated Execution — the orchestrator absorbs the retry/verify/unblock loop and returns a finished or verifiably-blocked result, not a half-step. The Inline loop below is the default for plan/spec files — **except when this command runs under the `wf-development` orchestration route in an autonomous mode (its fully-autonomous default, or `--final-review`)**, where Orchestrated is the default for all inputs: the orchestrator is a reviewer, not an implementer, and delegates every work item to a sub-agent whose diff it verifies before accepting.

1. **Task Execution Loop** (board mode — iterate open sub-issues)

   Work the claimed parent's **open sub-issues**. For multi-agent runs, each sub-issue is the claim unit — assign yourself (`gh issue edit <sub> --repo <origin> --add-assignee @me`) before starting it. Drive each sub-issue's `status:*` label through `--sub-status` at the boundaries so a stakeholder sees live state, and close it (via `done`) when — and only when — its acceptance criteria pass.

   ```
   while (open sub-issues of <N> remain):
     - sub = next open, unblocked sub-issue (from `gh issue view <N> --repo <origin> --json subIssues`)
     - (multi-agent) claim it: gh issue edit <sub> --repo <origin> --add-assignee @me
     - python3 "<skill-directory>/scripts/lifecycle_board.py" --sub-status <sub> in_progress
     - Read any referenced files from the plan
     - Look for similar patterns in the codebase
     - Implement following existing conventions
     - Write tests for new functionality
     - Run System-Wide Test Check (see below)
     - Run tests after changes
     - python3 "<skill-directory>/scripts/lifecycle_board.py" --sub-status <sub> in_review   # code done, awaiting acceptance verification
     - Verify acceptance criteria; when they pass:
     - python3 "<skill-directory>/scripts/lifecycle_board.py" --sub-status <sub> done   # strips the label AND closes the sub-issue
     - Check off the corresponding checkbox in the plan doc ([ ] → [x])  # readability only, non-authoritative
     - Evaluate for incremental commit (see below)
   ```

   `--sub-status … done` **replaces** the raw `gh issue close` — it strips the `status:*` label and closes the sub-issue as completed in one call. Mark a sub-issue `blocked` (`--sub-status <sub> blocked`) if you discover an open `blocked-by` while working it, and move it back to `in_progress` when unblocked. Never close the **parent** `<N>` here — the merge's "Item closed" automation stamps `shipped` for the parent downstream. Plan-doc checkboxes are non-authoritative doc content; still check them off so the plan reads as a living progress record, but the sub-issues (not the checkboxes) are the tracker.

   **Legacy flow** — no sub-issues exist; drive the existing **TodoWrite** loop instead:
   ```
   while (tasks remain):
     - Mark task in_progress in TodoWrite
     - Read referenced files; mirror existing patterns; implement; write tests
     - Run System-Wide Test Check; run tests
     - Mark task completed in TodoWrite
     - Check off the plan-doc checkbox ([ ] → [x])
     - Evaluate for incremental commit
   ```

   **System-Wide Test Check** — Before marking a task done, pause and ask:

   | Question | What to do |
   |----------|------------|
   | **What fires when this runs?** Callbacks, middleware, observers, event handlers — trace two levels out from your change. | Read the actual code (not docs) for callbacks on models you touch, middleware in the request chain, `after_*` hooks. |
   | **Do my tests exercise the real chain?** If every dependency is mocked, the test proves your logic works *in isolation* — it says nothing about the interaction. | Write at least one integration test that uses real objects through the full callback/middleware chain. No mocks for the layers that interact. |
   | **Can failure leave orphaned state?** If your code persists state (DB row, cache, file) before calling an external service, what happens when the service fails? Does retry create duplicates? | Trace the failure path with real objects. If state is created before the risky call, test that failure cleans up or that retry is idempotent. |
   | **What other interfaces expose this?** Mixins, DSLs, alternative entry points (Agent vs Chat vs ChatMethods). | Grep for the method/behavior in related classes. If parity is needed, add it now — not as a follow-up. |
   | **Do error strategies align across layers?** Retry middleware + application fallback + framework error handling — do they conflict or create double execution? | List the specific error classes at each layer. Verify your rescue list matches what the lower layer actually raises. |
   | **Does your code call an external library correctly?** If you import `X` and call `X.Y(args)`, are those args actually accepted by `Y`? Does the test suite exercise that call with real objects, or does it only test code *around* the call? | Run `help(X.Y)` or check the library's type stubs. If no test constructs a real `X.Y(...)`, write a smoke test. Passing tests that never reach the library call prove nothing about the integration. |

   **When to skip:** Leaf-node changes with no callbacks, no state persistence, no parallel interfaces. If the change is purely additive (new helper method, new view partial), the check takes 10 seconds and the answer is "nothing fires, skip."

   **When this matters most:** Any change that touches models with callbacks, error handling with fallback/retry, or functionality exposed through multiple interfaces.

   **IMPORTANT**: Always update the original plan document by checking off completed items. Use the Edit tool to change `- [ ]` to `- [x]` for each task you finish. This keeps the plan as a living document showing progress and ensures no checkboxes are left unchecked. (The sub-issues, not the checkboxes, are the authoritative tracker.)

2. **Incremental Commits**

   After completing each task, evaluate whether to create an incremental commit:

   | Commit when... | Don't commit when... |
   |----------------|---------------------|
   | Logical unit complete (model, service, component) | Small part of a larger unit |
   | Tests pass + meaningful progress | Tests failing |
   | About to switch contexts (backend → frontend) | Purely scaffolding with no behavior |
   | About to attempt risky/uncertain changes | Would need a "WIP" commit message |

   **Heuristic:** "Can I write a commit message that describes a complete, valuable change? If yes, commit. If the message would be 'WIP' or 'partial X', wait."

   **Commit workflow:**
   ```bash
   # 1. Verify tests pass (use project's test command)
   # Examples: bin/rails test, npm test, pytest, go test, etc.

   # 2. Stage only files related to this logical unit (not `git add .`)
   git add <files related to this logical unit>

   # 3. Commit with conventional message
   git commit -m "feat(scope): description of this unit"
   ```

   **Handling merge conflicts:** If conflicts arise during rebasing or merging, resolve them immediately. Incremental commits make conflict resolution easier since each commit is small and focused.

   **Note:** Incremental commits use clean conventional messages without attribution footers. The final Phase 4 commit/PR includes the full attribution.

3. **Follow Existing Patterns**

   - The plan should reference similar code — read those files first.
   - Match naming conventions exactly.
   - Reuse existing components where possible.
   - Follow project coding standards (see CLAUDE.md).
   - When in doubt, grep for similar implementations.

4. **Test Continuously**

   - Run relevant tests after each significant change.
   - Don't wait until the end to test.
   - Fix failures immediately.
   - Add new tests for new functionality.
   - **Unit tests with mocks prove logic in isolation. Integration tests with real objects prove the layers work together.** If your change touches callbacks, middleware, or error handling — you need both.
   - **External library smoke tests**: If you introduced a new library import or constructor call, write at least one test that constructs the real object with representative arguments. This catches API mismatches (wrong kwargs, missing parameters) that unit tests with mocks will never find.

5. **Figma Design Sync** (if applicable)

   For UI work with Figma designs:

   - Implement components following design specs.
   - Use figma-design-sync agent iteratively to compare.
   - Fix visual differences identified.
   - Repeat until implementation matches design.

6. **Track Progress**
   - Keep your tracker updated as you complete tasks — close each sub-issue (`gh issue close <sub> --repo <origin>`) when its criteria pass in board mode; TodoWrite otherwise.
   - Note any blockers or unexpected discoveries.
   - Create new sub-issues if scope expands (see the Orchestrated Execution binding for the follow-on recipe).
   - Keep the user informed of major milestones.

### Phase 3: Quality Check

1. **Run Core Quality Checks**

   Always run before submitting:

   ```bash
   # Run full test suite (use project's test command)
   # Examples: bin/rails test, npm test, pytest, go test, etc.

   # Run linting (per CLAUDE.md)
   # Use linting-agent before pushing to origin
   ```

2. **No open sub-issues** (board mode — REQUIRED before opening a PR)

   The parent work item **cannot enter `in_review` with open sub-issues**. Verify none remain:

   ```bash
   gh issue view <N> --repo <origin> --json subIssues
   ```

   If any sub-issue is still open, either finish and close it (`--sub-status <sub> done`), or (if it is genuinely out of scope for this PR) re-parent/close it deliberately — do not open the PR while the parent has open sub-issues. In the legacy flow this reduces to "all TodoWrite items checked."

   This is not just a checklist item: the engine **enforces** it. The Phase-4 `--set-status <N> in_review` write (below) **refuses with `open_sub_issues`** if any sub-issue is still open — so skipping this check surfaces a hard error rather than silently advancing an incomplete parent. Resolve the sub-issues, then the write succeeds.

3. **Integration Boundary Verification**

   Before submitting, for each external library call introduced or modified:

   a. **Identify integration boundaries**: Any `import` from an external package followed by a constructor or function call.

   b. **Verify at least one test exercises each boundary** with:
      - Real object construction (not a mock)
      - Representative arguments matching the library's actual API
      - Expected behavior assertion

   c. **For network-dependent code**: Use in-process servers, test fixtures, or localhost servers rather than mocking the entire library away.

   d. **Smoke test before committing**: If the feature has a UI or API endpoint, hit it once manually or via curl to verify it works end-to-end, not just in unit tests.

4. **Run an acceptance pre-check.** Compare the staged change against the work
   item's acceptance criteria and validation requirements while fixes are still
   cheap. This is advisory and never substitutes for the independent
   `wf-review` stage.

5. **Final Validation**
   - No open sub-issues on the parent (board mode), or all TodoWrite items checked (legacy)
   - All tests pass
   - Linting passes
   - Code follows existing patterns
   - Figma designs match (if applicable)
   - No console errors or warnings

6. **Prepare Operational Validation Plan** (REQUIRED)
   - Add a `## Post-Deploy Monitoring & Validation` section to the PR description for every change.
   - Include concrete:
     - Log queries/search terms
     - Metrics or dashboards to watch
     - Expected healthy signals
     - Failure signals and rollback/mitigation trigger
     - Validation window and owner
   - If there is truly no production/runtime impact, still include the section with: `No additional operational monitoring required` and a one-line reason.

### Phase 4: Ship It

The philosophy here: **opening the PR is the `in_review` transition, not a completion event.** The issue stays open. The merge — via `Closes #N` — is what closes the issue, and the built-in "Item closed" automation stamps `shipped`. This command's last board write is `in_review`; it never closes the issue and never writes a terminal stage.

1. **Create Commit**

   ```bash
   git add .
   git status  # Review what's being committed
   git diff --staged  # Check the changes

   # Commit with conventional format
   git commit -m "$(cat <<'EOF'
   feat(scope): description of what and why

   Brief explanation if needed.

   🤖 Generated with [Claude Code](https://claude.com/claude-code)

   Co-Authored-By: Claude <noreply@anthropic.com>
   EOF
   )"
   ```

2. **Collect user-visible evidence for interface changes.** Use `wf-testing`'s
   browser route and the repository-approved environment, accounts, browser
   mechanism, and artifact handling. Capture before/after or expected-state
   evidence when it helps review, and attach it through the repository's mapped
   delivery process. Do not assume a server command, URL, browser CLI, or upload
   provider.

3. **Create Pull Request**

   Open the PR against the **default branch** with a `Closes #<N>` line in the body, so the merge closes the issue and the automation stamps `shipped`:

   ```bash
   git push -u origin feat/<N>-<slug>

   gh pr create --repo <origin> --base [default_branch] --title "Feature: [Description]" --body "$(cat <<'EOF'
   Closes #<N>

   ## Summary
   - What was built
   - Why it was needed
   - Key decisions made

   ## Testing
   - Tests added/modified
   - Manual testing performed

   ## Post-Deploy Monitoring & Validation
   - **What to monitor/search**
     - Logs:
     - Metrics/Dashboards:
   - **Validation checks (queries/commands)**
     - `command or query here`
   - **Expected healthy behavior**
     - Expected signal(s)
   - **Failure signal(s) / rollback trigger**
     - Trigger + immediate action
   - **Validation window & owner**
     - Window:
     - Owner:
   - **If no operational impact**
     - `No additional operational monitoring required: <reason>`

   ## Before / After Screenshots
   | Before | After |
   |--------|-------|
   | ![before](URL) | ![after](URL) |

   ## Figma Design
   [Link if applicable]

   ---

   [![Compound Engineered](https://img.shields.io/badge/Compound-Engineered-6366f1)](https://github.com/aagnone3/agentic-engineering) 🤖 Generated with [Claude Code](https://claude.com/claude-code)
   EOF
   )"
   ```

   Capture the PR identifiers:

   ```bash
   PR_URL=$(gh pr view --repo <origin> --json url --jq '.url')
   PR_NUM=$(gh pr view --repo <origin> --json number --jq '.number')
   ```

4. **Advance the board to `in_review`** (board mode)

   The PR is open; move the work item to `in_review`. This is the command's second and final board write — **the issue is NOT closed here**:

   ```bash
   python3 "<skill-directory>/scripts/lifecycle_board.py" --set-status <N> in_review
   ```

   From here the lifecycle proceeds without any manual close protocol:
   - **On merge:** `Closes #<N>` closes the issue; the pre-enabled "Item closed" automation stamps `shipped`. No manual close, no frontmatter write.
   - **PR closed without merging:** the shared reconciler's closed repair set handles it — an assignee's PR closed unmerged regresses the item `in_review → in_progress` with an audit comment. There is no manual reopen protocol; the next `--reconcile` (Entry Gate step 2 on the next run, or a direct invocation) repairs it.

   In the **legacy flow**, skip this step — there is no board to advance; the PR is simply open.

5. **Notify User**
   - Summarize what was completed.
   - Link to the PR.
   - Note that the work item is now `in_review`; it becomes `shipped` automatically when the PR merges (and regresses to `in_progress` automatically if the PR is closed unmerged) — no manual tracking needed.
   - Note any follow-up work needed.
   - Suggest next steps: use the `wf-review` comprehensive-review route, then
     the `wf-delivery` landing route to drive CI green, resolve review threads,
     and merge once approved. This route ends at PR creation; `wf-delivery`
     owns the completion-and-merge tail.

---

## Orchestrated Execution (board-driven)

An execution style — available whenever the work item has tracked **sub-issues** — where instead
of implementing each sub-issue yourself inline, you act as the **orchestrator**: you own the board
and sub-issue state and delegate the actual implementation to **one focused subagent per sub-issue**,
looping each to a terminal state before returning to the user. It works for a **single sub-issue or a
whole set**.

Worth it even for one sub-issue: the orchestrator absorbs the iteration (retry on failed gates, verify
acceptance, discover and file follow-on work) so the user gets back a *finished or verifiably-
blocked* result, not a half-step.

**Orchestrated vs Swarm.** Orchestrated = you spawn one short-lived, tightly-scoped subagent per
sub-issue and verify each result yourself — tight control, ideal for one sub-issue or a modest set. Swarm
(below) = a team of long-lived teammates self-claim from a shared queue — maximum parallelism for
5+ independent workstreams. Use Orchestrated by default for tracked sub-issues; escalate to Swarm when
the set is large and highly parallel.

### GitHub binding (the single tracker)

All state lives on the board and its sub-issues. **Only the orchestrator** touches board/tracker state — subagents never do, and that includes every `--sub-status` write. Every `gh` write carries an explicit `--repo`/`--owner`.

| Action | GitHub |
|--------|--------|
| List ready | `python3 "<skill-directory>/scripts/lifecycle_board.py" --ready-work` (planned ∧ unassigned ∧ unblocked, Priority-sorted), or the open unblocked sub-issues of the claimed parent `<N>` via `gh issue view <N> --repo <origin> --json subIssues` |
| Read one | `gh issue view <sub> --repo <origin>` |
| Claim | assign yourself, then confirm: `gh issue edit <sub> --repo <origin> --add-assignee @me` — for the **parent**, use `--claim <N>` (it owns the full claim protocol) |
| Mark in progress | `lifecycle_board.py --sub-status <sub> in_progress` (at dispatch) |
| Mark in review | `lifecycle_board.py --sub-status <sub> in_review` (subagent returned; awaiting your verification) |
| Close (done) | `lifecycle_board.py --sub-status <sub> done` (when acceptance criteria pass — strips the label AND closes the sub-issue; use this instead of a raw `gh issue close`) |
| Block / needs human | `lifecycle_board.py --sub-status <sub> blocked`, then `gh issue edit <sub> --repo <origin> --add-blocked-by <blocker>` + `gh issue comment <sub> --repo <origin> --body "…"`, and surface the question |
| Add follow-on (gates parent) | `gh issue create --repo <origin> --parent <N> --blocked-by <sub> --title "…" --body-file …` so the new sub-issue gates the parent until it is closed |

The **parent** `<N>` is never closed inside the loop — its `shipped` stamp comes from the merge's "Item closed" automation (Phase 4). Close **sub-issues** as soon as their acceptance criteria pass and gates are green.

### Terminal conditions (a sub-issue is "done" when ONE holds)

1. **Resolved** — acceptance criteria met, quality gates pass, AND every follow-on sub-issue it spawned
   is also terminal. Close the sub-issue here; the parent is never closed in the loop (Phase 4 / the
   merge automation owns the parent's `shipped`).
2. **Blocked / needs human** — genuinely stuck on a decision, access, or ambiguity you can't
   resolve from the repo or the issue. Add a blocker (`gh issue edit <sub> --repo <origin> --add-blocked-by <blocker>`) or a `human`-labeled
   comment, surface the question — don't guess. (Terminal for this run; re-enters
   the loop once the user answers.)

Stop only when every target sub-issue — initial **and** spawned follow-ons — is in state 1 or 2. Never
report "done" while an open sub-issue is unstarted or a follow-on is open.

### Procedure

1. **Scope the set.** From the input: the parent `<N>` → its open sub-issues (`gh issue view <N> --repo <origin> --json subIssues`);
   explicit ids → those; none → `--ready-work`. Read each issue's body, acceptance criteria, and dependencies.
2. **Plan waves.** A wave = sub-issues ready now (no open `blocked-by`). Within a wave,
   split **parallel-safe** (file-disjoint — the plan usually names the files) from
   **must-serialize** (same files). Announce the plan briefly before dispatching.
3. **Dispatch.** Assign the sub-issue to yourself (`gh issue edit <sub> --repo <origin> --add-assignee @me`), mark it in progress (`lifecycle_board.py --sub-status <sub> in_progress`), then spawn one subagent per sub-issue with the brief below
   (Task tool / `general-purpose`, or a specialist agent). Send parallel dispatches in one message.
   The subagent implements only — **the orchestrator owns every `--sub-status` write**; the subagent never touches GitHub.
   For file-conflicting parallel work, isolate each agent with the bundled
   worktree manager and reconcile on return.
   **Model tiering:** run implementation subagents on an Opus-tier model (`model: "opus"`), in the
   background for parallel waves — the orchestrator keeps the session's strongest model for the
   verify/review step, and purely mechanical chores (docs regeneration, count bumps) can drop to a
   cheaper tier.
4. **Verify & branch** (orchestrator, per returned subagent):
   - On return, mark it awaiting verification: `lifecycle_board.py --sub-status <sub> in_review`.
   - Review the diff vs acceptance criteria; integrate any worktree.
   - Re-run the project's quality gates at the top level (catches cross-issue breakage one agent
     can't see).
   - **Met + clean** → `lifecycle_board.py --sub-status <sub> done` (strips the label and closes the sub-issue).
   - **Met + surfaced required work** → file follow-on(s): `gh issue create --repo <origin> --parent <N> --blocked-by <sub> …`
     so the parent can't complete early; add to the target set; then `--sub-status <sub> done`.
   - **Gates fail / criteria unmet** → `--sub-status <sub> in_progress` and loop (step 5). **Blocked** → `--sub-status <sub> blocked` and escalate (step 5).
5. **Loop or escalate.**
   - *Loop:* re-dispatch the same sub-issue with the specific failure appended ("tsc error X at
     file:line", "criterion N unmet"). Max ~2 retries.
   - *Escalate:* add a blocker + `human`-labeled comment, stop touching it, collect all such items, ask the
     user in ONE batch (AskUserQuestion). On reply: remove the blocker and re-dispatch.
6. **Next wave.** Re-check readiness (closing a sub-issue unblocks dependents and follow-ons). Repeat until
   the full set — initial and follow-ons — is terminal. Then proceed to Phase 3/4 for the PR
   (the merge, not this loop, stamps the parent `shipped`).

### Subagent brief template (copy, fill in)

```
You are implementing exactly one tracked sub-issue. Do ONLY this sub-issue.

SUB-ISSUE: <number> — <title>
<paste the full issue: body, design notes, acceptance criteria, dependencies>

CONTEXT:
- Repo + relevant existing files (the plan names them); patterns to mirror
- Conventions: match surrounding code, reuse existing components/helpers, do NOT add scope,
  backend, or features beyond this sub-issue. Keep the app runnable.

DO:
1. Verify through a channel independent of the one that produced the work and
   distinguish direct evidence from assumptions.
2. Implement the acceptance criteria — nothing more.
3. Run the repository's mapped quality gates. They must be clean.
4. Do NOT touch shared tracker state — the orchestrator owns it.

REPORT BACK (your final message = structured result, not prose to a human):
- Files created/modified (absolute paths)
- How each acceptance criterion is satisfied
- Exact gate results (tests? lint? type-check? build?)
- Assumptions made + anything needing a human decision (state blockers explicitly)
```

### Rules baked in
- Respect the dependency graph — never dispatch a sub-issue with an open `blocked-by`.
- Parallelize only file-disjoint sub-issues; otherwise serialize or isolate
  with this skill's [worktree reference](git-worktree.md) and bundled manager.
- One sub-issue = one subagent, tightly scoped; subagents never run board/tracker state changes.
- Discovered work becomes a follow-on sub-issue that gates its parent — never a silent extra.
- Bound retries (~2), then block and escalate — don't loop forever. A retry that makes no strictly-measurable progress (gates still fail the same way, no criterion newly satisfied) is a dry attempt; two dry attempts is the stall bound — the same uniform no-progress rule the `wf-development` orchestration route applies run-wide.
- Quality gates are mandatory before any sub-issue is closed; the parent's `shipped` comes from the merge.

---

## Swarm Mode (Optional)

For complex plans with multiple independent workstreams, enable swarm mode for parallel execution with coordinated agents.

### When to Use Swarm Mode

| Use Swarm Mode when... | Use Standard Mode when... |
|------------------------|---------------------------|
| Plan has 5+ independent tasks | Plan is linear/sequential |
| Multiple specialists needed (review + test + implement) | Single-focus work |
| Want maximum parallelism | Simpler mental model preferred |
| Large feature with clear phases | Small feature or bug fix |

### Enabling Swarm Mode

To trigger swarm execution, say:

> "Make a Task list and launch an army of agent swarm subagents to build the plan"

Or explicitly request: "Use swarm mode for this work"

### Swarm Workflow

When swarm mode is enabled, the workflow changes:

1. **Create Team**
   ```
   Teammate({ operation: "spawnTeam", team_name: "work-{timestamp}" })
   ```

2. **Create Task List with Dependencies**
   - Parse plan into TaskCreate items
   - Set up blockedBy relationships for sequential dependencies
   - Independent tasks have no blockers (can run in parallel)

3. **Spawn Specialized Teammates**
   ```
   Task({
     team_name: "work-{timestamp}",
     name: "implementer",
     subagent_type: "general-purpose",
     prompt: "Claim implementation tasks, execute, mark complete",
     run_in_background: true
   })

   Task({
     team_name: "work-{timestamp}",
     name: "tester",
     subagent_type: "general-purpose",
     prompt: "Claim testing tasks, run tests, mark complete",
     run_in_background: true
   })
   ```

4. **Coordinate and Monitor**
   - Team lead monitors task completion
   - Spawn additional workers as phases unblock
   - Handle plan approval if required

5. **Cleanup**
   ```
   Teammate({ operation: "requestShutdown", target_agent_id: "implementer" })
   Teammate({ operation: "requestShutdown", target_agent_id: "tester" })
   Teammate({ operation: "cleanup" })
   ```

Use only the host's documented agent-coordination capability. If the host has
no team or subagent mechanism, use the inline or orchestrated single-agent
model; do not require a separately named orchestration skill.

---

## Key Principles

### Start Fast, Execute Faster

- Get clarification once at the start, then execute
- Don't wait for perfect understanding - ask questions and move
- The goal is to **finish the feature**, not create perfect process

### The Plan is Your Guide

- Work documents should reference similar code and patterns
- Load those references and follow them
- Don't reinvent - match what exists

### Test As You Go

- Run tests after each change, not at the end
- Fix failures immediately
- Continuous testing prevents big surprises

### Quality is Built In

- Follow existing patterns
- Write tests for new code
- Run linting before pushing
- Use reviewer agents for complex/risky changes only

### Ship Complete Features

- Close every sub-issue before opening the PR
- Don't leave features 80% done
- A finished feature that ships beats a perfect feature that doesn't

## Quality Checklist

Before creating PR, verify:

- [ ] All clarifying questions asked and answered
- [ ] No open sub-issues on the parent `<N>` (`gh issue view <N> --repo <origin> --json subIssues`), or all TodoWrite items checked (legacy flow) — the parent is stamped `shipped` by the merge automation, never closed by this command
- [ ] Tests pass (run project's test command)
- [ ] Linting passes (use linting-agent)
- [ ] Code follows existing patterns
- [ ] Figma designs match implementation (if applicable)
- [ ] Before/after screenshots captured and uploaded (for UI changes)
- [ ] Commit messages follow conventional format
- [ ] PR body includes `Closes #<N>` and targets the default branch
- [ ] PR description includes Post-Deploy Monitoring & Validation section (or explicit no-impact rationale)
- [ ] PR description includes summary, testing notes, and screenshots
- [ ] PR description includes Compound Engineered badge

## When to Use Reviewer Agents

**Don't use by default.** Use reviewer agents only when:

- Large refactor affecting many files (10+)
- Security-sensitive changes (authentication, permissions, data access)
- Performance-critical code paths
- Complex algorithms or business logic
- User explicitly requests thorough review

For most features: tests + linting + following patterns is sufficient.

## Common Pitfalls to Avoid

- **Analysis paralysis** - Don't overthink, read the plan and execute
- **Skipping clarifying questions** - Ask now, not after building wrong thing
- **Ignoring plan references** - The plan has links for a reason
- **Testing at the end** - Test continuously or suffer later
- **Forgetting to track progress** - Close sub-issues as you finish them (board mode) or update TodoWrite (legacy), or lose track of what's done
- **Closing the issue at PR creation** - Don't. Opening the PR is the `in_review` transition; the *merge* closes the issue via `Closes #<N>` and the automation stamps `shipped`. Manually closing at PR-open subverts the automation and the reconciler's repairs
- **Opening the PR with open sub-issues** - The parent can't enter `in_review` with open sub-issues; finish or deliberately re-scope them first
- **Over-reviewing simple changes** - Save reviewer agents for complex work
