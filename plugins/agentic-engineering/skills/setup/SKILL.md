---
name: setup
description: Configure which review agents run for your project. Auto-detects stack and writes agentic-engineering.local.md.
disable-model-invocation: true
---

# Agentic Engineering Setup

Interactive setup for `agentic-engineering.local.md` — configures which agents run during `/workflows:review` and `/workflows:work`.

## Step 1: Check Existing Config

Read `agentic-engineering.local.md` in the project root. If it exists, display current settings summary and use AskUserQuestion:

```
question: "Settings file already exists. What would you like to do?"
header: "Config"
options:
  - label: "Reconfigure"
    description: "Run the interactive setup again from scratch"
  - label: "View current"
    description: "Show the file contents, then stop"
  - label: "Cancel"
    description: "Keep current settings"
```

If "View current": read and display the file, then stop.
If "Cancel": stop.

## Step 2: Detect and Ask

Auto-detect the project stack:

```bash
test -f Gemfile && test -f config/routes.rb && echo "rails" || \
test -f Gemfile && echo "ruby" || \
test -f tsconfig.json && echo "typescript" || \
test -f package.json && echo "javascript" || \
test -f pyproject.toml && echo "python" || \
test -f requirements.txt && echo "python" || \
echo "general"
```

Use AskUserQuestion:

```
question: "Detected {type} project. How would you like to configure?"
header: "Setup"
options:
  - label: "Auto-configure (Recommended)"
    description: "Use smart defaults for {type}. Done in one click."
  - label: "Customize"
    description: "Choose stack, focus areas, and review depth."
```

### If Auto-configure → Skip to Step 4 with defaults:

- **Rails:** `[kieran-rails-reviewer, dhh-rails-reviewer, code-simplicity-reviewer, security-sentinel, performance-oracle]`
- **Python:** `[kieran-python-reviewer, code-simplicity-reviewer, security-sentinel, performance-oracle]`
- **TypeScript:** `[kieran-typescript-reviewer, code-simplicity-reviewer, security-sentinel, performance-oracle]`
- **General:** `[code-simplicity-reviewer, security-sentinel, performance-oracle, architecture-strategist]`

### If Customize → Step 3

## Step 3: Customize (3 questions)

**a. Stack** — confirm or override:

```
question: "Which stack should we optimize for?"
header: "Stack"
options:
  - label: "{detected_type} (Recommended)"
    description: "Auto-detected from project files"
  - label: "Rails"
    description: "Ruby on Rails — adds DHH-style and Rails-specific reviewers"
  - label: "Python"
    description: "Python — adds Pythonic pattern reviewer"
  - label: "TypeScript"
    description: "TypeScript — adds type safety reviewer"
```

Only show options that differ from the detected type.

**b. Focus areas** — multiSelect:

```
question: "Which review areas matter most?"
header: "Focus"
multiSelect: true
options:
  - label: "Security"
    description: "Vulnerability scanning, auth, input validation (security-sentinel)"
  - label: "Performance"
    description: "N+1 queries, memory leaks, complexity (performance-oracle)"
  - label: "Architecture"
    description: "Design patterns, SOLID, separation of concerns (architecture-strategist)"
  - label: "Code simplicity"
    description: "Over-engineering, YAGNI violations (code-simplicity-reviewer)"
```

**c. Depth:**

```
question: "How thorough should reviews be?"
header: "Depth"
options:
  - label: "Thorough (Recommended)"
    description: "Stack reviewers + all selected focus agents."
  - label: "Fast"
    description: "Stack reviewers + code simplicity only. Less context, quicker."
  - label: "Comprehensive"
    description: "All above + git history, data integrity, agent-native checks."
```

## Step 3.5: Detect Issue Tracker

Run the preflight script to discover the auto-detected tracker:

```bash
TRACKER=$(python3 "${CLAUDE_PLUGIN_ROOT}/scripts/workflow-repo-preflight.py" 2>/dev/null | jq -r '.integrations.issue_tracker_resolved // "none"')
```

`TRACKER` is one of `github-project`, `github`, or `none`. Record it in the generated config (next
step). The auto-detect chain — committed board config (`agentic-engineering.md` with
`github_project_owner` + `github_project_number`) → `github-project`; `gh auth status` succeeds →
`github`; otherwise → `none` — runs every time the workflows are invoked, but recording the explicit
value makes resolution deterministic. Beads no longer participates in tracker resolution; it remains
available only as an optional, non-authoritative scratchpad for an implementer's own working notes
(`bd remember`), never as a lifecycle source of truth.

## Step 3.6: Lifecycle board (optional but recommended)

If the project wants lifecycle tracking on GitHub Projects v2 (`github-project` mode) rather than
plain issue tracking, offer to bootstrap the board now:

```
question: "Set up a GitHub Projects v2 lifecycle board for this repo?"
header: "Lifecycle board"
options:
  - label: "Yes, bootstrap it"
    description: "Creates the project, configures the 9-stage Status field, and writes committed board config."
  - label: "Skip"
    description: "Stay on plain github/none tracker mode for now — can be run later."
```

If yes, run the bootstrap script:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/bootstrap_lifecycle_board.py"
```

The script creates the project, rewrites the built-in Status field's options **ID-preservingly**
(so existing automations stay wired to the renamed options), adds a Priority field, disables the
"Item reopened" workflow **if present** (new projects typically don't ship it; `/lifecycle-doctor`
re-checks — where present it would otherwise stamp a reopened issue back to `stub`, erasing its
lifecycle position), and writes the **committed** config file `agentic-engineering.md`
at the repo root with `github_project_owner` and `github_project_number`. This file must be
committed (not `.local`) — fresh clones and worktree-isolated subagents need to resolve the same
board identity.

Two steps have no API and stay manual:

1. **Auto-add-from-repo** — configure the board's auto-add workflow in the GitHub UI so new issues
   land on the board at the `stub` column.
2. **Ready-work saved view** — create a saved view filtered to `status:planned no:assignee`, sorted
   by Priority. Note it over-shows blocked items (the view has no way to filter on blocked-by), so
   check an item's Blocked-by field before starting work on it.

After bootstrapping (and after the two manual steps), run `/lifecycle-doctor` to verify the board
schema, automations, and config all resolve correctly before relying on it.

## Step 4: Build Agent List and Write File

**Stack-specific agents:**
- Rails → `kieran-rails-reviewer, dhh-rails-reviewer`
- Python → `kieran-python-reviewer`
- TypeScript → `kieran-typescript-reviewer`
- General → (none)

**Focus area agents:**
- Security → `security-sentinel`
- Performance → `performance-oracle`
- Architecture → `architecture-strategist`
- Code simplicity → `code-simplicity-reviewer`

**Depth:**
- Thorough: stack + selected focus areas
- Fast: stack + `code-simplicity-reviewer` only
- Comprehensive: all above + `git-history-analyzer, data-integrity-guardian, agent-native-reviewer, integration-boundary-reviewer`

**Plan review agents:** stack-specific reviewer + `code-simplicity-reviewer`.

Write `agentic-engineering.local.md`:

```markdown
---
issue_tracker: {detected tracker}    # github-project | github | none
review_agents: [{computed agent list}]
plan_review_agents: [{computed plan agent list}]
---

# Review Context

Add project-specific review instructions here.
These notes are passed to all review agents during /workflows:review and /workflows:work.

Examples:
- "We use Turbo Frames heavily — check for frame-busting issues"
- "Our API is public — extra scrutiny on input validation"
- "Performance-critical: we serve 10k req/s on this endpoint"
```

## Step 5: Confirm

```
Saved to agentic-engineering.local.md

Stack:         {type}
Issue tracker: {tracker}    # github-project, github, or none
Review depth:  {depth}
Agents:        {count} configured
               {agent list, one per line}

Tip: Edit the "Review Context" section to add project-specific instructions.
     Change issue_tracker: in the frontmatter to switch trackers (github-project, github, none).
     Re-run this setup anytime to reconfigure.
     Run /lifecycle-doctor anytime to verify the lifecycle board is wired correctly.
```
