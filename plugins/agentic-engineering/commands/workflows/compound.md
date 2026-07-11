---
name: workflows:compound
description: Document a recently solved problem to compound your team's knowledge
argument-hint: "[optional: brief context about the fix]"
---

# /compound

Coordinate multiple subagents working in parallel to document a recently solved problem.

## Purpose

Captures problem solutions while context is fresh, creating structured documentation in `docs/solutions/` with YAML frontmatter for searchability and future reference. Uses parallel subagents for maximum efficiency.

**Why "compound"?** Each documented solution compounds your team's knowledge. The first time you solve a problem takes research. Document it, and the next occurrence takes minutes. Knowledge compounds.

## Usage

```bash
/workflows:compound                    # Document the most recent fix
/workflows:compound [brief context]    # Provide additional context hint
```

## Entry Gate (run before anything else)

**Writer contract:** this command performs exactly one transition: `shipped|deployed → compounded`.

1. Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/lifecycle_board.py" --gate compound [--issue <N>]` (pass `--issue` only if the fix being documented is join-keyed to a tracked issue; omit it for hotfixes with no board item).
2. Branch on `verdict` — exactly these outcomes, nothing else:
   - **`proceed`**, no issue (hotfix path) → continue to Phase 1; do not stamp any status — there is nothing to stamp.
   - **`proceed`**, issue at `shipped`/`deployed` → continue to Phase 1; this run owns the write to `compounded` after the doc is written (Phase 2 step 6).
   - **`already_done`** (already `compounded`) → report: "Issue #<N> is already compounded — nothing to do." Then STOP.
   - **`repair_needed`** (issue exists but stage is pre-merge, i.e. not yet `shipped`) → continue to Phase 1 and document anyway (documenting doesn't require the merge to have landed), but do **not** stamp `compounded` — the issue hasn't shipped yet.
   - **`no_board`** (no board configured / legacy repo) → continue to Phase 1 using the legacy flow (no lifecycle write in Phase 2 step 6).

Stage semantics and mechanics: load the `lifecycle` skill.

## Execution Strategy: Two-Phase Orchestration

<critical_requirement>
**Only ONE file gets written - the final documentation.**

Phase 1 subagents return TEXT DATA to the orchestrator. They must NOT use Write, Edit, or create any files. Only the orchestrator (Phase 2) writes the final documentation file.
</critical_requirement>

### Phase 1: Parallel Research

<parallel_tasks>

Launch these subagents IN PARALLEL. Each returns text data to the orchestrator.

#### 1. **Context Analyzer**
   - Extracts conversation history
   - Identifies problem type, component, symptoms
   - Validates against schema
   - Returns: YAML frontmatter skeleton

#### 2. **Solution Extractor**
   - Analyzes all investigation steps
   - Identifies root cause
   - Extracts working solution with code examples
   - Returns: Solution content block

#### 3. **Related Docs Finder**
   - Searches `docs/solutions/` for related documentation
   - Identifies cross-references and links
   - Finds related GitHub issues
   - Returns: Links and relationships

#### 4. **Prevention Strategist**
   - Develops prevention strategies
   - Creates best practices guidance
   - Generates test cases if applicable
   - Returns: Prevention/testing content

#### 5. **Category Classifier**
   - Determines optimal `docs/solutions/` category
   - Validates category against schema
   - Suggests filename based on slug
   - Returns: Final path and filename

</parallel_tasks>

### Phase 2: Assembly & Write

<sequential_tasks>

**WAIT for all Phase 1 subagents to complete before proceeding.**

The orchestrating agent (main conversation) performs these steps:

1. Collect all text results from Phase 1 subagents
2. Assemble complete markdown file from the collected pieces
3. Validate YAML frontmatter against schema
4. Create directory if needed: `mkdir -p docs/solutions/[category]/`
5. Write the SINGLE final file: `docs/solutions/[category]/[filename].md`
6. **Lifecycle stamp** — only if the Entry Gate verdict was `proceed` with a `shipped`/`deployed` issue (never for the hotfix no-issue path, never for `repair_needed`, never if the gate returned `no_board`):
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/lifecycle_board.py" --set-status <N> compounded
   ```
7. If `bd` is on PATH (check via the preflight script's `integrations.beads_remember_available`), record a one-line insight pointing back to the solution doc — this is tracker-independent knowledge memory, not a lifecycle write:
   ```bash
   bd remember "<one-line insight>" --link "docs/solutions/[category]/[filename].md"
   ```
   This is universal — it runs whenever `bd` is installed, regardless of the resolved issue tracker. It complements the solution doc; it does not replace it. Skip silently if `bd` is not available.

</sequential_tasks>

### Phase 3: Ship the knowledge as its own PR (the data lane)

**WAIT for Phase 2 to complete before proceeding.**

Phase 2 wrote markdown into the working tree — but writing a file is not shipping it. Left there, the
knowledge sits uncommitted on the (post-merge) default branch and the session has to turn back and ask
the user what to do. Instead, **spin the docs off into their own PR and land it autonomously.** The
data is markdown-only and low-risk, so it does not need the code PR's review gate — it needs a PR and a
merge.

Invoke the [`land-docs`](../../skills/land-docs/SKILL.md) skill with the source issue number:

```
skill: land-docs <N>
```

`land-docs` opens a **docs-only** PR (`docs/<N>-knowledge`) **with GitHub auto-merge armed at
creation**, then follows its GitHub Actions checks:

- **checks pass** → GitHub auto-merges (squash, delete branch) on its own — no user turn, and it
  lands even if the session has already ended;
- **a check fails and the fix is simple** → fixes it, pushes, re-checks (auto-merge stays armed);
- **a check fails and it warrants input** → pauses and asks the user.

The knowledge PR is **always submitted with auto-merge enabled** — the merge is pre-committed the
moment the PR opens, gated only by the docs-only scope check.

It enforces one safety property: the diff must be **100% documentation** (`*.md`, `docs/**`). Any
non-doc path aborts the auto-merge and escalates. This is what makes the merge safe to do unattended.

**When to run the data lane:**

- **Autonomous pipeline** (`/workflows:orchestrate`, or `/workflows:compound` invoked as the pipeline's
  compound stage) → run it automatically. This is the seam that used to bounce back to the user.
- **Standalone `/workflows:compound`** → run it too, so a hand-invoked compound also closes out without
  a manual "now open a PR for these docs" step.
- **`no_board` / hotfix with no issue** → still applies; `land-docs` uses `compound` as the branch/PR
  slug when no `<N>` is available.

The old blocking "What's next?" decision menu in the `compound-docs` skill is **suppressed** on this
path — routing to `land-docs` *is* "what's next."

### Phase 4: Optional Enhancement

**WAIT for Phase 3 to complete before proceeding.**

<parallel_tasks>

Based on problem type, optionally invoke specialized agents to review the documentation. These are
in-agent enhancers, not a merge gate — the docs PR's review is owned by CI (`land-docs`). Run them
before Phase 3 if you want their edits included in the PR; skip freely for a straightforward capture:

- **performance_issue** → `performance-oracle`
- **security_issue** → `security-sentinel`
- **database_issue** → `data-integrity-guardian`
- **test_failure** → `cora-test-reviewer`
- Any code-heavy issue → `kieran-rails-reviewer` + `code-simplicity-reviewer`

</parallel_tasks>

## What It Captures

- **Problem symptom**: Exact error messages, observable behavior
- **Investigation steps tried**: What didn't work and why
- **Root cause analysis**: Technical explanation
- **Working solution**: Step-by-step fix with code examples
- **Prevention strategies**: How to avoid in future
- **Cross-references**: Links to related issues and docs

## Preconditions

<preconditions enforcement="advisory">
  <check condition="problem_solved">
    Problem has been solved (not in-progress)
  </check>
  <check condition="solution_verified">
    Solution has been verified working
  </check>
  <check condition="non_trivial">
    Non-trivial problem (not simple typo or obvious error)
  </check>
</preconditions>

## What It Creates

**Organized documentation:**

- File: `docs/solutions/[category]/[filename].md`

**Categories auto-detected from problem:**

- build-errors/
- test-failures/
- runtime-errors/
- performance-issues/
- database-issues/
- security-issues/
- ui-bugs/
- integration-issues/
- logic-errors/

## Common Mistakes to Avoid

| ❌ Wrong | ✅ Correct |
|----------|-----------|
| Subagents write files like `context-analysis.md`, `solution-draft.md` | Subagents return text data; orchestrator writes one final file |
| Research and assembly run in parallel | Research completes → then assembly runs |
| Multiple files created during workflow | Single file: `docs/solutions/[category]/[filename].md` |

## Success Output

```
✓ Documentation complete

Subagent Results:
  ✓ Context Analyzer: Identified performance_issue in brief_system
  ✓ Solution Extractor: 3 code fixes
  ✓ Related Docs Finder: 2 related issues
  ✓ Prevention Strategist: Prevention strategies, test suggestions
  ✓ Category Classifier: `performance-issues`

Specialized Agent Reviews (Auto-Triggered):
  ✓ performance-oracle: Validated query optimization approach
  ✓ kieran-rails-reviewer: Code examples meet Rails standards
  ✓ code-simplicity-reviewer: Solution is appropriately minimal
  ✓ editorial-style-editor: Documentation style verified

File created:
- docs/solutions/performance-issues/n-plus-one-brief-generation.md

This documentation will be searchable for future reference when similar
issues occur in the Email Processing or Brief System modules.

What's next?
1. Continue workflow (recommended)
2. Link related documentation
3. Update other references
4. View documentation
5. Other
```

## The Compounding Philosophy

This creates a compounding knowledge system:

1. First time you solve "N+1 query in brief generation" → Research (30 min)
2. Document the solution → docs/solutions/performance-issues/n-plus-one-briefs.md (5 min)
3. Next time similar issue occurs → Quick lookup (2 min)
4. Knowledge compounds → Team gets smarter

The feedback loop:

```
Build → Test → Find Issue → Research → Improve → Document → Validate → Deploy
    ↑                                                                      ↓
    └──────────────────────────────────────────────────────────────────────┘
```

**Each unit of engineering work should make subsequent units of work easier—not harder.**

## Auto-Invoke

<auto_invoke> <trigger_phrases> - "that worked" - "it's fixed" - "working now" - "problem solved" </trigger_phrases>

<manual_override> Use /workflows:compound [context] to document immediately without waiting for auto-detection. </manual_override> </auto_invoke>

## Routes To

- `compound-docs` skill — writes the single documentation file (Phases 1–2).
- `land-docs` skill — ships that file as its own docs-only PR and merges it on green (Phase 3).

## Applicable Specialized Agents

Based on problem type, these agents can enhance documentation:

### Code Quality & Review
- **kieran-rails-reviewer**: Reviews code examples for Rails best practices
- **code-simplicity-reviewer**: Ensures solution code is minimal and clear
- **pattern-recognition-specialist**: Identifies anti-patterns or repeating issues

### Specific Domain Experts
- **performance-oracle**: Analyzes performance_issue category solutions
- **security-sentinel**: Reviews security_issue solutions for vulnerabilities
- **cora-test-reviewer**: Creates test cases for prevention strategies
- **data-integrity-guardian**: Reviews database_issue migrations and queries

### Enhancement & Documentation
- **best-practices-researcher**: Enriches solution with industry best practices
- **editorial-style-editor**: Reviews documentation style and clarity
- **framework-docs-researcher**: Links to Rails/gem documentation references

### When to Invoke
- **Auto-triggered** (optional): Agents can run post-documentation for enhancement
- **Manual trigger**: User can invoke agents after /workflows:compound completes for deeper review
- **Customize agents**: Edit `agentic-engineering.local.md` or invoke the `setup` skill to configure which review agents are used across all workflows

## Related Commands

- `/research [topic]` - Deep investigation (searches docs/solutions/ for patterns)
- `/workflows:plan` - Planning workflow (references documented solutions)
