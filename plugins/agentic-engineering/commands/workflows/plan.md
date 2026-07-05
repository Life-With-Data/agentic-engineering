---
name: workflows:plan
description: Transform feature descriptions into well-structured project plans following conventions
argument-hint: "[feature description, bug report, or improvement idea]"
---

# Create a plan for a new feature or bug fix

## Introduction

**Note: The current year is 2026.** Use this when dating plans and searching for recent documentation.

Transform feature descriptions, bug reports, or improvement ideas into well-structured markdown files issues that follow project conventions and best practices. This command provides flexible detail levels to match your needs.

## Feature Description

<feature_description> #$ARGUMENTS </feature_description>

**If the feature description above is empty, ask the user:** "What would you like to plan? Please describe the feature, bug fix, or improvement you have in mind."

Do not proceed until you have a clear feature description from the user.

### 0. Idea Refinement

**Check for brainstorm output first:**

Before asking questions, look for recent brainstorm documents in `docs/brainstorms/` that match this feature:

```bash
ls -la docs/brainstorms/*.md 2>/dev/null | head -10
```

**Relevance criteria:** A brainstorm is relevant if:
- The topic (from filename or YAML frontmatter) semantically matches the feature description
- Created within the last 14 days
- If multiple candidates match, use the most recent one

**If a relevant brainstorm exists:**
1. Read the brainstorm document **thoroughly** — every section matters
2. Announce: "Found brainstorm from [date]: [topic]. Using as foundation for planning."
3. Extract and carry forward **ALL** of the following into the plan:
   - Key decisions and their rationale
   - Chosen approach and why alternatives were rejected
   - Constraints and requirements discovered during brainstorming
   - Open questions (flag these for resolution during planning)
   - Success criteria and scope boundaries
   - Any specific technical choices or patterns discussed
4. **Skip the idea refinement questions below** — the brainstorm already answered WHAT to build
5. Use brainstorm content as the **primary input** to research and planning phases
6. **Critical: The brainstorm is the origin document.** Throughout the plan, reference specific decisions with `(see brainstorm: docs/brainstorms/<filename>)` when carrying forward conclusions. Do not paraphrase decisions in a way that loses their original context — link back to the source.
7. **Do not omit brainstorm content** — if the brainstorm discussed it, the plan must address it (even if briefly). Scan each brainstorm section before finalizing the plan to verify nothing was dropped.

**If multiple brainstorms could match:**
Use **AskUserQuestion tool** to ask which brainstorm to use, or whether to proceed without one.

**If no brainstorm found (or not relevant), run idea refinement:**

Refine the idea through collaborative dialogue using the **AskUserQuestion tool**:

- Ask questions one at a time to understand the idea fully
- Prefer multiple choice questions when natural options exist
- Focus on understanding: purpose, constraints and success criteria
- Continue until the idea is clear OR user says "proceed"

**Gather signals for research decision.** During refinement, note:

- **User's familiarity**: Do they know the codebase patterns? Are they pointing to examples?
- **User's intent**: Speed vs thoroughness? Exploration vs execution?
- **Topic risk**: Security, payments, external APIs warrant more caution
- **Uncertainty level**: Is the approach clear or open-ended?

**Skip option:** If the feature description is already detailed, offer:
"Your description is clear. Should I proceed with research, or would you like to refine it further?"

## Main Tasks

### 1. Local Research (Always Runs - Parallel)

<thinking>
First, I need to understand the project's conventions, existing patterns, and any documented learnings. This is fast and local - it informs whether external research is needed.
</thinking>

Run these agents **in parallel** to gather local context:

- Task repo-research-analyst(feature_description)
- Task learnings-researcher(feature_description)

**What to look for:**
- **Repo research:** existing patterns, CLAUDE.md guidance, technology familiarity, pattern consistency
- **Learnings:** documented solutions in `docs/solutions/` that might apply (gotchas, patterns, lessons learned)

These findings inform the next step.

### 1.5. Research Decision

Based on signals from Step 0 and findings from Step 1, decide on external research.

**High-risk topics → always research.** Security, payments, external APIs, data privacy. The cost of missing something is too high. This takes precedence over speed signals.

**Strong local context → skip external research.** Codebase has good patterns, CLAUDE.md has guidance, user knows what they want. External research adds little value.

**Uncertainty or unfamiliar territory → research.** User is exploring, codebase has no examples, new technology. External perspective is valuable.

**Announce the decision and proceed.** Brief explanation, then continue. User can redirect if needed.

Examples:
- "Your codebase has solid patterns for this. Proceeding without external research."
- "This involves payment processing, so I'll research current best practices first."

### 1.5b. External Research (Conditional)

**Only run if Step 1.5 indicates external research is valuable.**

Run these agents in parallel:

- Task best-practices-researcher(feature_description)
- Task framework-docs-researcher(feature_description)

### 1.6. Consolidate Research

After all research steps complete, consolidate findings:

- Document relevant file paths from repo research (e.g., `app/services/example_service.rb:42`)
- **Include relevant institutional learnings** from `docs/solutions/` (key insights, gotchas to avoid)
- Note external documentation URLs and best practices (if external research was done)
- List related issues or PRs discovered
- Capture CLAUDE.md conventions

**Optional validation:** Briefly summarize findings and ask if anything looks off or missing before proceeding to planning.

### 2. Issue Planning & Structure

<thinking>
Think like a product manager - what would make this issue clear and actionable? Consider multiple perspectives
</thinking>

**Title & Categorization:**

- [ ] Draft clear, searchable issue title using conventional format (e.g., `feat: Add user authentication`, `fix: Cart total calculation`)
- [ ] Determine issue type: enhancement, bug, refactor
- [ ] Convert title to filename: add today's date prefix, strip prefix colon, kebab-case, add `-plan` suffix
  - Example: `feat: Add User Authentication` → `2026-01-21-feat-add-user-authentication-plan.md`
  - Keep it descriptive (3-5 words after prefix) so plans are findable by context

**Stakeholder Analysis:**

- [ ] Identify who will be affected by this issue (end users, developers, operations)
- [ ] Consider implementation complexity and required expertise

**Content Planning:**

- [ ] Choose appropriate detail level based on issue complexity and audience
- [ ] List all necessary sections for the chosen template
- [ ] Gather supporting materials (error logs, screenshots, design mockups)
- [ ] Prepare code examples or reproduction steps if applicable, name the mock filenames in the lists

### 3. SpecFlow Analysis

After planning the issue structure, run SpecFlow Analyzer to validate and refine the feature specification:

- Task agentic-engineering:workflow:spec-flow-analyzer(feature_description, research_findings)

**SpecFlow Analyzer Output:**

- [ ] Review SpecFlow analysis results
- [ ] Incorporate any identified gaps or edge cases into the issue
- [ ] Update acceptance criteria based on SpecFlow findings

### 4. Choose Implementation Detail Level

Select how comprehensive you want the issue to be, simpler is mostly better.

**Tracker-ID frontmatter contract (applies to all three templates below):**

Every plan exiting `/workflows:plan` must record exactly one of:

```
bead_id: bd-NNN          # when issue_tracker == "beads"
github_issue: 123        # when issue_tracker == "github"
```

The field is populated by mandatory Step 7 (Create Tracker Issue) — templates show only the `bead_id:` placeholder for brevity. The Stop hook at `scripts/plan-tracker-guard.py` blocks turn termination if a created/edited plan lacks one of these fields and is not opted out via `issue_tracker: none`.

#### 📄 MINIMAL (Quick Issue)

**Best for:** Simple bugs, small improvements, clear features

**Includes:**

- Problem statement or feature description
- Basic acceptance criteria
- Essential context only

**Structure:**

````markdown
---
title: [Issue Title]
type: [feat|fix|refactor]
status: active
date: YYYY-MM-DD
origin: docs/brainstorms/YYYY-MM-DD-<topic>-brainstorm.md  # if originated from brainstorm, otherwise omit
bead_id: bd-NNN          # REQUIRED — see "Tracker-ID frontmatter contract" in Section 4
---

# [Issue Title]

[Brief problem/feature description]

## Acceptance Criteria

- [ ] Core requirement 1
- [ ] Core requirement 2

## Context

[Any critical information]

## MVP

### test.rb

```ruby
class Test
  def initialize
    @name = "test"
  end
end
```

## Sources

- **Origin brainstorm:** [docs/brainstorms/YYYY-MM-DD-<topic>-brainstorm.md](path) — include if plan originated from a brainstorm
- Related issue: #[issue_number]
- Documentation: [relevant_docs_url]
````

#### 📋 MORE (Standard Issue)

**Best for:** Most features, complex bugs, team collaboration

**Includes everything from MINIMAL plus:**

- Detailed background and motivation
- Technical considerations
- Success metrics
- Dependencies and risks
- Basic implementation suggestions

**Structure:**

```markdown
---
title: [Issue Title]
type: [feat|fix|refactor]
status: active
date: YYYY-MM-DD
origin: docs/brainstorms/YYYY-MM-DD-<topic>-brainstorm.md  # if originated from brainstorm, otherwise omit
bead_id: bd-NNN          # REQUIRED — see "Tracker-ID frontmatter contract" in Section 4
---

# [Issue Title]

## Overview

[Comprehensive description]

## Problem Statement / Motivation

[Why this matters]

## Proposed Solution

[High-level approach]

## Technical Considerations

- Architecture impacts
- Performance implications
- Security considerations

## System-Wide Impact

- **Interaction graph**: [What callbacks/middleware/observers fire when this runs?]
- **Error propagation**: [How do errors flow across layers? Do retry strategies align?]
- **State lifecycle risks**: [Can partial failure leave orphaned/inconsistent state?]
- **API surface parity**: [What other interfaces expose similar functionality and need the same change?]
- **Integration test scenarios**: [Cross-layer scenarios that unit tests won't catch]

## External System Wiring

**REQUIRED.** For each external system this feature integrates with, document:

- **System name and console URL** (e.g., Clerk Dashboard, Stripe Dashboard, Slack App config, GitHub App settings).
- **Configuration objects this feature requires** (webhook endpoints, OAuth apps, scopes, event subscriptions, API credentials, signing secrets).
- **Where the configuration lives** (provider UI, IaC repo, manual env var).
- **Host-side wiring this feature requires** (middleware allowlist additions, env var scope, redirect URL allowlists, DNS records).
- **Verification step** that proves the external config is live (not just that the code compiles or that unit tests pass). The strongest form is "send a test event from the provider's dashboard and observe X in our logs."

If the feature is purely internal (no third-party config, no env vars beyond defaults, no auth/middleware allowlist changes), state explicitly: **"No external wiring required."**

## Acceptance Criteria

- [ ] Detailed requirement 1
- [ ] Detailed requirement 2
- [ ] Testing requirements

## Success Metrics

[How we measure success]

## Dependencies & Risks

[What could block or complicate this]

## Sources & References

- **Origin brainstorm:** [docs/brainstorms/YYYY-MM-DD-<topic>-brainstorm.md](path) — include if plan originated from a brainstorm
- Similar implementations: [file_path:line_number]
- Best practices: [documentation_url]
- Related PRs: #[pr_number]
```

#### 📚 A LOT (Comprehensive Issue)

**Best for:** Major features, architectural changes, complex integrations

**Includes everything from MORE plus:**

- Detailed implementation plan with phases
- Alternative approaches considered
- Extensive technical specifications
- Resource requirements and timeline
- Future considerations and extensibility
- Risk mitigation strategies
- Documentation requirements

**Structure:**

```markdown
---
title: [Issue Title]
type: [feat|fix|refactor]
status: active
date: YYYY-MM-DD
origin: docs/brainstorms/YYYY-MM-DD-<topic>-brainstorm.md  # if originated from brainstorm, otherwise omit
bead_id: bd-NNN          # REQUIRED — see "Tracker-ID frontmatter contract" in Section 4
---

# [Issue Title]

## Overview

[Executive summary]

## Problem Statement

[Detailed problem analysis]

## Proposed Solution

[Comprehensive solution design]

## Technical Approach

### Architecture

[Detailed technical design]

### Implementation Phases

#### Phase 1: [Foundation]

- Tasks and deliverables
- Success criteria
- Estimated effort

#### Phase 2: [Core Implementation]

- Tasks and deliverables
- Success criteria
- Estimated effort

#### Phase 3: [Polish & Optimization]

- Tasks and deliverables
- Success criteria
- Estimated effort

## Alternative Approaches Considered

[Other solutions evaluated and why rejected]

## System-Wide Impact

### Interaction Graph

[Map the chain reaction: what callbacks, middleware, observers, and event handlers fire when this code runs? Trace at least two levels deep. Document: "Action X triggers Y, which calls Z, which persists W."]

### External System Wiring

**REQUIRED.** For each external system this feature integrates with, document:

- **System name and console URL** (e.g., Clerk Dashboard, Stripe Dashboard, Slack App config, GitHub App settings).
- **Configuration objects this feature requires** (webhook endpoints, OAuth apps, scopes, event subscriptions, API credentials, signing secrets).
- **Where the configuration lives** (provider UI, IaC repo, manual env var).
- **Host-side wiring this feature requires** (middleware allowlist additions, env var scope, redirect URL allowlists, DNS records).
- **Verification step** that proves the external config is live (not just that the code compiles or that unit tests pass). The strongest form is "send a test event from the provider's dashboard and observe X in our logs."

The receiver code can ship in days; the provider-side subscription and host-side allowlist are dashboard-and-env-var work that's invisible to PR review. Without this section, the next webhook integration, the next OAuth provider, the next external-API listener will ship with a one-sided wiring and fail silently on first user-facing smoke test.

If the feature is purely internal (no third-party config, no env vars beyond defaults, no auth/middleware allowlist changes), state explicitly: **"No external wiring required."**

### Error & Failure Propagation

[Trace errors from lowest layer up. List specific error classes and where they're handled. Identify retry conflicts, unhandled error types, and silent failure swallowing.]

### State Lifecycle Risks

[Walk through each step that persists state. Can partial failure orphan rows, duplicate records, or leave caches stale? Document cleanup mechanisms or their absence.]

### API Surface Parity

[List all interfaces (classes, DSLs, endpoints) that expose equivalent functionality. Note which need updating and which share the code path.]

### Integration Test Scenarios

[3-5 cross-layer test scenarios that unit tests with mocks would never catch. Include expected behavior for each.]

## Acceptance Criteria

### Functional Requirements

- [ ] Detailed functional criteria

### Non-Functional Requirements

- [ ] Performance targets
- [ ] Security requirements
- [ ] Accessibility standards

### Quality Gates

- [ ] Test coverage requirements
- [ ] Documentation completeness
- [ ] Code review approval

## Success Metrics

[Detailed KPIs and measurement methods]

## Dependencies & Prerequisites

[Detailed dependency analysis]

## Risk Analysis & Mitigation

[Comprehensive risk assessment]

## Resource Requirements

[Team, time, infrastructure needs]

## Future Considerations

[Extensibility and long-term vision]

## Documentation Plan

[What docs need updating]

## Sources & References

### Origin

- **Brainstorm document:** [docs/brainstorms/YYYY-MM-DD-<topic>-brainstorm.md](path) — include if plan originated from a brainstorm. Key decisions carried forward: [list 2-3 major decisions from brainstorm]

### Internal References

- Architecture decisions: [file_path:line_number]
- Similar features: [file_path:line_number]
- Configuration: [file_path:line_number]

### External References

- Framework documentation: [url]
- Best practices guide: [url]
- Industry standards: [url]

### Related Work

- Previous PRs: #[pr_numbers]
- Related issues: #[issue_numbers]
- Design documents: [links]
```

### 5. Issue Creation & Formatting

<thinking>
Apply best practices for clarity and actionability, making the issue easy to scan and understand
</thinking>

**Content Formatting:**

- [ ] Use clear, descriptive headings with proper hierarchy (##, ###)
- [ ] Include code examples in triple backticks with language syntax highlighting
- [ ] Add screenshots/mockups if UI-related (drag & drop or use image hosting)
- [ ] Use task lists (- [ ]) for trackable items that can be checked off
- [ ] Add collapsible sections for lengthy logs or optional details using `<details>` tags
- [ ] Apply appropriate emoji for visual scanning (🐛 bug, ✨ feature, 📚 docs, ♻️ refactor)

**Cross-Referencing:**

- [ ] Link to related issues/PRs using #number format
- [ ] Reference specific commits with SHA hashes when relevant
- [ ] Link to code using GitHub's permalink feature (press 'y' for permanent link)
- [ ] Mention relevant team members with @username if needed
- [ ] Add links to external resources with descriptive text

**Code & Examples:**

````markdown
# Good example with syntax highlighting and line references


```ruby
# app/services/user_service.rb:42
def process_user(user)

# Implementation here

end
```

# Collapsible error logs

<details>
<summary>Full error stacktrace</summary>

`Error details here...`

</details>
````

**AI-Era Considerations:**

- [ ] Account for accelerated development with AI pair programming
- [ ] Include prompts or instructions that worked well during research
- [ ] Note which AI tools were used for initial exploration (Claude, Copilot, etc.)
- [ ] Emphasize comprehensive testing given rapid implementation
- [ ] Document any AI-generated code that needs human review

### 6. Final Review & Submission

**Brainstorm cross-check (if plan originated from a brainstorm):**

Before finalizing, re-read the brainstorm document and verify:
- [ ] Every key decision from the brainstorm is reflected in the plan
- [ ] The chosen approach matches what was decided in the brainstorm
- [ ] Constraints and requirements from the brainstorm are captured in acceptance criteria
- [ ] Open questions from the brainstorm are either resolved or flagged
- [ ] The `origin:` frontmatter field points to the brainstorm file
- [ ] The Sources section includes the brainstorm with a summary of carried-forward decisions

**Pre-submission Checklist:**

- [ ] Title is searchable and descriptive
- [ ] Labels accurately categorize the issue
- [ ] All template sections are complete
- [ ] Links and references are working
- [ ] Acceptance criteria are measurable
- [ ] Add names of files in pseudo code examples and todo lists
- [ ] Add an ERD mermaid diagram if applicable for new model changes

## Write Plan File

**REQUIRED: Write the plan file to disk before presenting any options.**

```bash
mkdir -p docs/plans/
```

Use the Write tool to save the complete plan to `docs/plans/YYYY-MM-DD-<type>-<descriptive-name>-plan.md`. This step is mandatory and cannot be skipped — even when running as part of LFG/SLFG or other automated pipelines.

Confirm: "Plan written to docs/plans/[filename]"

**Pipeline mode:** If invoked from an automated workflow (LFG, SLFG, or any `disable-model-invocation` context), skip all AskUserQuestion calls. Make decisions automatically and proceed to writing the plan without interactive prompts.

## Output Format

**Filename:** Use the date and kebab-case filename from Step 2 Title & Categorization.

```
docs/plans/YYYY-MM-DD-<type>-<descriptive-name>-plan.md
```

Examples:
- ✅ `docs/plans/2026-01-15-feat-user-authentication-flow-plan.md`
- ✅ `docs/plans/2026-02-03-fix-checkout-race-condition-plan.md`
- ✅ `docs/plans/2026-03-10-refactor-api-client-extraction-plan.md`
- ❌ `docs/plans/2026-01-15-feat-thing-plan.md` (not descriptive - what "thing"?)
- ❌ `docs/plans/2026-01-15-feat-new-feature-plan.md` (too vague - what feature?)
- ❌ `docs/plans/2026-01-15-feat: user auth-plan.md` (invalid characters - colon and space)
- ❌ `docs/plans/feat-user-auth-plan.md` (missing date prefix)

## Step 7. Create Tracker Issue (MANDATORY)

**This step is a gate, not an option.** Every plan that exits `/workflows:plan` must have a tracker issue recorded in its frontmatter (`bead_id` or `github_issue`). This step runs unconditionally — including in LFG/SLFG/`disable-model-invocation` pipeline mode. Only `AskUserQuestion` calls are skipped in pipeline mode; tracker creation itself still executes.

**Resolve the issue tracker first** — run the preflight script and read `integrations.issue_tracker_resolved`:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/workflow-repo-preflight.py" | jq -r '.integrations'
```

Print a one-line banner before acting:
```
Tracker: <resolved> (<source>)
```

Then dispatch on `issue_tracker_resolved`:

### `beads`

```bash
bd create \
  --title "<type>: <title>" \
  --description "Plan: <plan_path>\n\n$(head -40 <plan_path>)" \
  --type=feature \
  --priority=2 \
  --design="<one-paragraph approach summary from the plan>" \
  --notes="<context links: brainstorm origin, related PRs>"
```

Capture the returned bead ID (e.g. `bd-123`) and write it back into the plan file's YAML frontmatter as `bead_id: bd-123`. If the plan originated from a brainstorm that also has a `bead_id:`, run `bd dep add <plan-bead> <brainstorm-bead>` to link them.

If `bd` is not on PATH (which should not happen if preflight resolved to `beads`), STOP and surface the error — do not proceed to Post-Generation Options without a tracker ID.

### `github`

```bash
gh issue create --title "<type>: <title>" --body-file <plan_path>
```

Capture the returned issue number and write `github_issue: <N>` back into the plan frontmatter.

### `none`

Print:
```
No issue tracker detected. Install `bd` (https://github.com/gastownhall/beads) or run `gh auth login` to enable issue creation. Plan file is saved at <plan_path>.
```

This is the only path that may exit Step 7 without writing a tracker ID. When this happens, Post-Generation Options MUST surface the lack of tracking in its preamble and MUST NOT offer `/workflows:work` as a next step.

Verification of the recorded tracker ID happens once, at the top of Post-Generation Options below — that's the menu gate.

## Post-Generation Options

<!-- AskUserQuestion constraint: 2-4 options max -->

**Precondition assertion (re-verify before opening any question):**

Before presenting Question 1, re-read the plan file's YAML frontmatter and verify that exactly one of `bead_id` or `github_issue` is populated — OR that Step 7 ran and resolved `issue_tracker == none` (the documented un-tracked carve-out).

If none of those fields exist and Step 7 did not record an explicit `none` resolution, **STOP** and re-run Step 7 (Create Tracker Issue). Do not advance to the questions below until either a tracker ID is in the frontmatter or the `none` carve-out is confirmed. This guards against agents that skip Step 7 or fail it silently.

After verification, open the plan in the user's default editor:

```bash
open docs/plans/<plan_filename>.md
```

Then use the **AskUserQuestion tool** to present these options:

**Question 1 preamble — pick the right phrasing based on the recorded tracker:**

- If a tracker ID is present: `"Plan ready at docs/plans/YYYY-MM-DD-<type>-<name>-plan.md (tracked as <bead_id|github_issue>, opened in editor). What would you like to do next?"`
- If `issue_tracker == none` carve-out: `"Plan ready at docs/plans/YYYY-MM-DD-<type>-<name>-plan.md (UNTRACKED — no issue tracker detected). What would you like to do next?"`

**Options (4 max):**
1. **Run `/deepen-plan`** - Enhance with parallel research agents (best practices, performance, UI)
2. **Run `/technical_review`** - Technical feedback from code-focused reviewers
3. **Start `/workflows:work`** - Begin implementing (add `&` suffix for background/remote execution). **Omit this option entirely when the `none` carve-out is active** — work must not start without a tracker ID.
4. **Review and refine** - Structured self-review via `document-review` skill

Based on selection:
- **`/deepen-plan`** → Call the /deepen-plan command with the plan file path to enhance with research
- **`/technical_review`** → Call the /technical_review command with the plan file path
- **`/workflows:work`** → Call the /workflows:work command with the plan file path. For remote/web execution, run with `&` to start in background.
- **Review and refine** → Load `document-review` skill.

**Question 2 (after action completes, only if user did NOT pick `/workflows:work`):**

Use the **AskUserQuestion tool** again:

**Question:** "What would you like to do next?"

**Options (2):**
1. **Start `/workflows:work`** - Begin implementing this plan (omit when the `none` carve-out is active)
2. **Continue refining** - Loop back to Question 1

Based on selection:
- **`/workflows:work`** → Call the /workflows:work command with the plan file path
- **Continue refining** → Loop back to Question 1

**Note:** If running `/workflows:plan` with ultrathink enabled, automatically run `/deepen-plan` after plan creation for maximum depth and grounding.

NEVER CODE! Just research and write the plan.
