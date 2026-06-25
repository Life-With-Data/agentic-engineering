---
name: workflows:work
description: Execute work plans efficiently while maintaining quality and finishing features
argument-hint: "[plan file, specification, or todo file path]"
---

# Work Plan Execution Command

Execute a work plan efficiently while maintaining quality and finishing features.

## Introduction

This command takes a work document (plan, specification, or todo file) and executes it systematically. The focus is on **shipping complete features** by understanding requirements quickly, following existing patterns, and maintaining quality throughout.

## Input Document

<input_document> #$ARGUMENTS </input_document>

## Execution Workflow

### Phase 1: Quick Start

1. **Read Plan and Clarify**

   - Read the work document completely
   - Review any references or links provided in the plan
   - If anything is unclear or ambiguous, ask clarifying questions now
   - Get user approval to proceed
   - **Do not skip this** - better to ask questions now than build the wrong thing

2. **Setup Environment**

   First, run the repo preflight script and use its JSON output as the source of truth for branch state, dirty state, PR context, and issue-tracker availability:

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/workflow-repo-preflight.py"
   ```

   The script returns:
   - `repo.current_branch`
   - `repo.default_branch`
   - `repo.working_tree_dirty`
   - `github.current_branch_pr` (if `gh` is installed/authenticated)
   - `integrations.linear_api_key_present`
   - `integrations.beads_installed`, `integrations.beads_initialized`
   - `integrations.issue_tracker_resolved` — one of `beads | linear | github | none`
   - `integrations.issue_tracker_source` — `agentic-engineering.local.md`, `auto-detect`, or `default`
   - `integrations.issue_tracker_ambiguous` — `true` when both `.beads/` and `LINEAR_API_KEY` are present
   - `recommendation.action` and `recommendation.prompt`

   Print a one-line tracker banner before continuing:
   ```
   Tracker: <issue_tracker_resolved> (<issue_tracker_source>)
   ```
   If `issue_tracker_ambiguous` is `true`, append: `— set issue_tracker: in agentic-engineering.local.md to override`.

   Follow `recommendation.action` rather than re-deriving state manually.

   **If already on a feature branch** (not the default branch):
   - Ask: "Continue working on `[current_branch]`, or create a new branch?"
   - If continuing, proceed to step 3
   - If creating new, follow Option A or B below

   **If on the default branch**, choose how to proceed:

   **Option A: Create a new branch**
   ```bash
   git pull origin [default_branch]
   git checkout -b feature-branch-name
   ```
   Use a meaningful name based on the work (e.g., `feat/user-authentication`, `fix/email-validation`).

   **Option B: Use a worktree (recommended for parallel development)**
   ```bash
   skill: git-worktree
   # The skill will create a new branch from the default branch in an isolated worktree
   ```

   **Option C: Continue on the default branch**
   - Requires explicit user confirmation
   - Only proceed after user explicitly says "yes, commit to [default_branch]"
   - Never commit directly to the default branch without explicit permission

   **Recommendation**: Use worktree if:
   - You want to work on multiple features simultaneously
   - You want to keep the default branch clean while experimenting
   - You plan to switch between branches frequently

3. **Sync with tracker**

   Dispatch on `integrations.issue_tracker_resolved`:

   - **`beads`**: `bd dolt pull` (no-op if no Dolt remote is configured).
   - **`linear`**:
     ```bash
     agentic-plugin linear pull --todos-dir ./todos
     agentic-plugin linear push --file <plan-or-todo-path>
     ```
     Silently skips if `LINEAR_API_KEY` is not set.
   - **`github`**: no sync step.
   - **`none`**: skip.

4. **Create Task List**

   Dispatch on `integrations.issue_tracker_resolved`:

   - **`beads`** — create one bead per actionable task in the plan and link to the parent plan bead:
     ```bash
     # PLAN_BEAD=$(yq '.bead_id' <plan-path>)  # if plan frontmatter has it
     for task in <tasks from plan>:
       TASK_ID=$(bd q --title="<task>" --description="..." --type=task --priority=<map>)
       bd dep add "$TASK_ID" "$PLAN_BEAD"   # only if PLAN_BEAD is set
     ```
     Do **not** use TodoWrite when tracker is `beads` — `bd ready` supersedes it.

   - **`linear` / `github` / `none`** — use TodoWrite (existing behavior):
     - Break the plan into actionable tasks
     - Include dependencies between tasks
     - Prioritize based on what needs to be done first
     - Include testing and quality check tasks
     - Keep tasks specific and completable

### Phase 2: Execute

1. **Task Execution Loop**

   The claim/complete steps depend on `integrations.issue_tracker_resolved`.

   > **Parent bead vs child task beads.** If the job is a single standalone bead (the common `bd ready` flow — one bead = the whole feature), it is the **parent** and gets closed in Phase 4 once the PR is open. Only **child task beads** of a parent plan get closed inside the loop below, because they represent local units of work that don't ship their own PR. When in doubt, leave the bead open and let Phase 4 handle the close.

   **When tracker is `beads`:**

   First, decide which mode you're in:

   - **Standalone bead mode** — Phase 1 set no `PLAN_BEAD` (the job is a single bead with no child tasks). **Skip this entire loop.** Implement directly, test, commit, then go to Phase 3 / Phase 4. The bead stays `in_progress` through implementation; Phase 4 closes it after PR creation.
   - **Plan-with-children mode** — Phase 1 set `PLAN_BEAD` from plan frontmatter and created child task beads linked via `bd dep add`. Run the loop below, filtered to those children so `bd ready` cannot return the parent.

   Then pick an **execution style** for whichever mode you're in:

   - **Inline** (default) — you implement each bead directly in this session (the loop below, or
     "implement directly" for a standalone bead).
   - **Orchestrated** — you act as orchestrator and delegate each bead to a focused subagent,
     looping it to a terminal state (resolved or *verified blocker*) before moving on. Prefer this
     when the user invokes it, when beads are file-disjoint (parallelizable), or when you want the
     iteration (retry / verify / unblock / discovered-follow-on) handled before returning. It works
     for a single bead too. See [Orchestrated Execution](#orchestrated-execution-delegate-beads-to-subagents).
     The bead-close rules are identical to inline: child beads close in the loop; the parent/
     standalone bead is closed in Phase 4 after the PR.

   ```
   # Plan-with-children mode only. PLAN_BEAD must be set.
   while (bd ready --json | jq -e --arg p "$PLAN_BEAD" '[.[] | select(.parent==$p)] | length > 0'):
     - id=$(bd ready --json | jq -r --arg p "$PLAN_BEAD" '[.[] | select(.parent==$p)][0].id')
     - bd update $id --claim
     - Read any referenced files from the plan
     - Look for similar patterns in codebase
     - Implement following existing conventions
     - Write tests for new functionality
     - Run System-Wide Test Check (see below)
     - Run tests after changes
     - bd close $id      # child task beads only — never the parent bead $PLAN_BEAD
     - Mark off the corresponding checkbox in the plan file ([ ] → [x])
     - Evaluate for incremental commit (see below)
   ```

   Do not close `$PLAN_BEAD` here under any condition. Phase 4 owns its close, after the PR is created.

   **When tracker is `linear`, `github`, or `none`** — use the existing TodoWrite-driven loop:
   ```
   while (tasks remain):
     - Mark task as in_progress in TodoWrite
     - Read any referenced files from the plan
     - Look for similar patterns in codebase
     - Implement following existing conventions
     - Write tests for new functionality
     - Run System-Wide Test Check (see below)
     - Run tests after changes
     - Mark task as completed in TodoWrite
     - Mark off the corresponding checkbox in the plan file ([ ] → [x])
     - Evaluate for incremental commit (see below)
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

   **IMPORTANT**: Always update the original plan document by checking off completed items. Use the Edit tool to change `- [ ]` to `- [x]` for each task you finish. This keeps the plan as a living document showing progress and ensures no checkboxes are left unchecked.

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

   - The plan should reference similar code - read those files first
   - Match naming conventions exactly
   - Reuse existing components where possible
   - Follow project coding standards (see CLAUDE.md)
   - When in doubt, grep for similar implementations

4. **Test Continuously**

   - Run relevant tests after each significant change
   - Don't wait until the end to test
   - Fix failures immediately
   - Add new tests for new functionality
   - **Unit tests with mocks prove logic in isolation. Integration tests with real objects prove the layers work together.** If your change touches callbacks, middleware, or error handling — you need both.
   - **External library smoke tests**: If you introduced a new library import or constructor call, write at least one test that constructs the real object with representative arguments. This catches API mismatches (wrong kwargs, missing parameters) that unit tests with mocks will never find.

5. **Figma Design Sync** (if applicable)

   For UI work with Figma designs:

   - Implement components following design specs
   - Use figma-design-sync agent iteratively to compare
   - Fix visual differences identified
   - Repeat until implementation matches design

6. **Track Progress**
   - Keep your tracker updated as you complete tasks (`bd update`/`bd close` when `issue_tracker: beads`, TodoWrite otherwise).
   - Note any blockers or unexpected discoveries.
   - Create new tasks if scope expands.
   - Keep user informed of major milestones.

### Phase 3: Quality Check

1. **Run Core Quality Checks**

   Always run before submitting:

   ```bash
   # Run full test suite (use project's test command)
   # Examples: bin/rails test, npm test, pytest, go test, etc.

   # Run linting (per CLAUDE.md)
   # Use linting-agent before pushing to origin
   ```

2. **Integration Boundary Verification**

   Before submitting, for each external library call introduced or modified:

   a. **Identify integration boundaries**: Any `import` from an external package followed by a constructor or function call.

   b. **Verify at least one test exercises each boundary** with:
      - Real object construction (not a mock)
      - Representative arguments matching the library's actual API
      - Expected behavior assertion

   c. **For network-dependent code**: Use in-process servers, test fixtures, or localhost servers rather than mocking the entire library away.

   d. **Smoke test before committing**: If the feature has a UI or API endpoint, hit it once manually or via curl to verify it works end-to-end, not just in unit tests.

3. **Consider Reviewer Agents** (Optional)

   Use for complex, risky, or large changes. Read agents from `agentic-engineering.local.md` frontmatter (`review_agents`). If no settings file, invoke the `setup` skill to create one.

   Run configured agents in parallel with Task tool. Present findings and address critical issues.

4. **Final Validation**
   - All tracker tasks marked completed (`bd list --status=open --parent=<plan-bead>` returns empty, or all TodoWrite items checked)
   - All tests pass
   - Linting passes
   - Code follows existing patterns
   - Figma designs match (if applicable)
   - No console errors or warnings

5. **Prepare Operational Validation Plan** (REQUIRED)
   - Add a `## Post-Deploy Monitoring & Validation` section to the PR description for every change.
   - Include concrete:
     - Log queries/search terms
     - Metrics or dashboards to watch
     - Expected healthy signals
     - Failure signals and rollback/mitigation trigger
     - Validation window and owner
   - If there is truly no production/runtime impact, still include the section with: `No additional operational monitoring required` and a one-line reason.

### Phase 4: Ship It

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

2. **Capture and Upload Screenshots for UI Changes** (REQUIRED for any UI work)

   For **any** design changes, new views, or UI modifications, you MUST capture and upload screenshots:

   **Step 1: Start dev server** (if not running)
   ```bash
   bin/dev  # Run in background
   ```

   **Step 2: Capture screenshots with agent-browser CLI**
   ```bash
   agent-browser open http://localhost:3000/[route]
   agent-browser snapshot -i
   agent-browser screenshot output.png
   ```
   See the `agent-browser` skill for detailed usage.

   **Step 3: Upload using imgup skill**
   ```bash
   skill: imgup
   # Then upload each screenshot:
   imgup -h pixhost screenshot.png  # pixhost works without API key
   # Alternative hosts: catbox, imagebin, beeimg
   ```

   **What to capture:**
   - **New screens**: Screenshot of the new UI
   - **Modified screens**: Before AND after screenshots
   - **Design implementation**: Screenshot showing Figma design match

   **IMPORTANT**: Always include uploaded image URLs in PR description. This provides visual context for reviewers and documents the change.

3. **Create Pull Request**

   ```bash
   git push -u origin feature-branch-name

   gh pr create --title "Feature: [Description]" --body "$(cat <<'EOF'
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

   Capture the PR identifiers — Phase 4 needs them:

   ```bash
   PR_URL=$(gh pr view --json url --jq '.url')
   PR_NUM=$(gh pr view --json number --jq '.number')
   ```

4. **Close Tracker Item**

   PR creation is the bead's completion event. The work is in the PR; the merge is downstream ratification. Closing here avoids the friction of a manual post-merge cleanup step that humans and agents reliably forget — leaving beads perpetually open after the code has long since shipped.

   If the input document has YAML frontmatter with a `status` field, update it to `completed`:
   ```
   status: active  →  status: completed
   ```

   Dispatch on `integrations.issue_tracker_resolved`:

   - **`beads`**:
     ```bash
     # PLAN_BEAD is either the parent bead from plan frontmatter, or the standalone
     # bead claimed in Phase 1.
     PLAN_BEAD=${PLAN_BEAD:-$(yq '.bead_id' <plan-path>)}
     bd close "$PLAN_BEAD" --reason="PR #${PR_NUM}: ${PR_URL}"
     bd dolt push   # no-op if Dolt remote unconfigured
     ```
   - **`linear`**:
     ```bash
     agentic-plugin linear push --file <plan-or-todo-path>
     ```
     Silently skips if `LINEAR_API_KEY` is not set.
   - **`github`**:
     ```bash
     gh issue close <issue-number> --comment "PR #${PR_NUM}: ${PR_URL}"
     ```
   - **`none`**: skip.

   **Exception — PR rejected or substantially revised after open.** If a PR is later closed without merging, or sent back for a rewrite that takes weeks, reopen the bead with `bd update "$PLAN_BEAD" --status=in_progress --append-notes "PR #N closed without merge: <reason>"`. This is rare in solo and small-team workflows; treat it as a manual exception rather than designing the default around it.

5. **Notify User**
   - Summarize what was completed
   - Link to PR
   - Note that the bead is closed and will reopen only if the PR is rejected
   - Note any follow-up work needed
   - Suggest next steps if applicable

---

## Orchestrated Execution (delegate beads to subagents)

An execution style for the **beads** tracker where, instead of implementing each bead yourself
inline, you act as the **orchestrator**: you own the bead state machine and delegate the actual
implementation to **one focused subagent per bead**, looping each bead to a terminal state before
returning to the user. It works for a **single bead or a whole set**.

Worth it even for one bead: the orchestrator absorbs the iteration (retry on failed gates, verify
acceptance, discover and file follow-on work) so the user gets back a *finished or verifiably-
blocked* result, not a half-step.

**Orchestrated vs Swarm.** Orchestrated = you spawn one short-lived, tightly-scoped subagent per
bead and verify each result yourself — tight control, ideal for one bead or a modest set. Swarm
(below) = a team of long-lived teammates self-claim from a shared queue — maximum parallelism for
5+ independent workstreams. Use Orchestrated by default for tracked beads; escalate to Swarm when
the set is large and highly parallel.

### Terminal conditions (a bead is "done" when ONE holds)

1. **Resolved** — acceptance criteria met, quality gates pass, AND every follow-on bead it spawned
   is also terminal. Close child beads here; the parent/standalone bead is closed in **Phase 4**
   after the PR (per the parent-vs-child rule above) — never inside the loop.
2. **Blocked / needs human** — genuinely stuck on a decision, access, or ambiguity you can't
   resolve from the repo or the bead. `bd update <id> --status=blocked --notes="…"` and
   `bd label add <id> human`, surface the question — don't guess. (Terminal for this run; re-enters
   the loop once the user answers.)

Stop only when every target bead — initial **and** spawned follow-ons — is in state 1 or 2. Never
report "done" while a ready bead is unstarted or a follow-on is open.

### Procedure

1. **Scope the set.** From the input: an epic/parent id → its children (`bd show <id>`); explicit
   ids → those; none → `bd ready`. Read each bead's description, design, acceptance, and deps.
2. **Plan waves.** A wave = beads ready now (no open blockers, via `bd ready`). Within a wave,
   split **parallel-safe** (file-disjoint — the design notes usually name the files) from
   **must-serialize** (same files). Announce the plan briefly before dispatching.
3. **Dispatch.** `bd update <id> --claim`, then spawn one subagent per bead with the brief below
   (Task tool / `general-purpose`, or a specialist agent). Send parallel dispatches in one message.
   For file-conflicting parallel work, isolate each agent in its own git worktree (`skill: git-worktree`) and reconcile on return.
4. **Verify & branch** (orchestrator, per returned subagent):
   - Review the diff vs acceptance criteria; integrate any worktree.
   - Re-run the project's quality gates at the top level (catches cross-bead breakage one agent
     can't see).
   - **Met + clean, is a child bead** → `bd close <id> --reason="…" --suggest-next`.
   - **Met + surfaced required work** → file follow-on(s): `bd create … --deps discovered-from:<id>`
     then `bd dep add <parent> <new>` so the parent can't close early; add to the target set;
     then close this child.
   - **Met, is the parent/standalone bead** → leave open; Phase 4 closes it after the PR.
   - **Gates fail / criteria unmet** → loop (step 5). **Blocked** → escalate (step 5).
5. **Loop or escalate.**
   - *Loop:* re-dispatch the same bead with the specific failure appended ("tsc error X at
     file:line", "criterion N unmet"). Max ~2 retries.
   - *Escalate:* mark blocked + `human` label, stop touching it, collect all such items, ask the
     user in ONE batch (AskUserQuestion). On reply: reopen (`--status=open`) and re-dispatch.
6. **Next wave.** Re-check `bd ready` (closing unblocks dependents and follow-ons). Repeat until
   the full set — initial and follow-ons — is terminal. Then proceed to Phase 3/4 for the PR
   (which closes the parent/standalone bead).

### Subagent brief template (copy, fill in)

```
You are implementing exactly one bead. Do ONLY this bead.

BEAD: <id> — <title>
<paste full `bd show <id>`: description, design notes, acceptance criteria, dependencies>

CONTEXT:
- Repo + relevant existing files (the design names them); patterns to mirror
- Conventions: match surrounding code, reuse existing components/helpers, do NOT add scope,
  backend, or features beyond this bead. Keep the app runnable.

DO:
1. Implement the acceptance criteria — nothing more.
2. Run this project's quality gates (tests + lint + type-check + build as applicable). Must be clean.
3. Do NOT change bead state (no claim/close/block) — the orchestrator owns that.

REPORT BACK (your final message = structured result, not prose to a human):
- Files created/modified (absolute paths)
- How each acceptance criterion is satisfied
- Exact gate results (tests? lint? type-check? build?)
- Assumptions made + anything needing a human decision (state blockers explicitly)
```

### Rules baked in
- Respect the dependency graph — never dispatch a blocked bead.
- Parallelize only file-disjoint beads; otherwise serialize or isolate with the `git-worktree` skill.
- One bead = one subagent, tightly scoped; subagents never run bead state changes.
- Discovered work becomes a follow-on bead that gates its parent — never a silent extra.
- Bound retries (~2), then mark blocked and escalate — don't loop forever.
- Quality gates are mandatory before any bead is closed; the parent/standalone bead closes in Phase 4.

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

See the `orchestrating-swarms` skill for detailed swarm patterns and best practices.

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

- Mark all tasks completed before moving on
- Don't leave features 80% done
- A finished feature that ships beats a perfect feature that doesn't

## Quality Checklist

Before creating PR, verify:

- [ ] All clarifying questions asked and answered
- [ ] All **child task** beads closed (`bd list --status=open --parent=<plan-bead>` is empty), or all TodoWrite items checked — the parent/standalone bead gets closed in Phase 4 after PR creation
- [ ] Tests pass (run project's test command)
- [ ] Linting passes (use linting-agent)
- [ ] Code follows existing patterns
- [ ] Figma designs match implementation (if applicable)
- [ ] Before/after screenshots captured and uploaded (for UI changes)
- [ ] Commit messages follow conventional format
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
- **Forgetting to track progress** - Update your tracker (`bd` or TodoWrite) as you go, or lose track of what's done
- **80% done syndrome** - Finish the feature, don't move on early
- **Forgetting to close the bead after PR creation** - The bead represents the work, not the merge. Close it in Phase 4 with the PR reference. If the PR is later rejected, reopen with `bd update --status=in_progress` — that's the rare exception, not the rule
- **Over-reviewing simple changes** - Save reviewer agents for complex work
