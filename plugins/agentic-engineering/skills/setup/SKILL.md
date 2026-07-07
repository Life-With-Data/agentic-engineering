---
name: setup
description: Configure which review agents run for your project. Auto-detects stack, writes agentic-engineering.local.md, and offers to bootstrap the lifecycle board and install the operating-principles always-on layer into CLAUDE.md/AGENTS.md.
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

If yes, first decide **how new issues should reach the board** — a real choice, not a formality.
Projects v2 boards are *materialized collections, not live queries*: creating an issue does **not**
put it on any board, and GitHub's auto-add workflow is **forward-only** (it never backfills). So the
setup records **two orthogonal decisions** (backfill is relevant under *any* forward choice — never
gate it behind auto-add).

**(A) Forward binding — how NEW issues reach the board.** Ask with AskUserQuestion:

```
question: "How should new issues reach the lifecycle board?"
header: "Forward binding"
options:
  - label: "Workflow-only (recommended)"
    description: "The /workflows:* commands add items themselves as they plan/work. No auto-add, no standing token."
  - label: "Auto-add new issues"
    description: "Bootstrap scaffolds an actions/add-to-project workflow so every new issue auto-lands. Needs a PAT secret. Forward-only."
  - label: "None / manual"
    description: "Add issues to the board by hand."
```

Run the bootstrap with the chosen binding (map the answer to `workflow-only` | `auto-add` | `none`;
omit the flag to accept the default or preserve a prior choice on re-run):

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/bootstrap_lifecycle_board.py" --forward-binding <workflow-only|auto-add|none>
```

The script creates the project, rewrites the built-in Status field's options **ID-preservingly**
(so existing automations stay wired to the renamed options), adds a Priority field, disables the
"Item reopened" workflow **if present** (new projects typically don't ship it; `/lifecycle-doctor`
re-checks — where present it would otherwise stamp a reopened issue back to `stub`, erasing its
lifecycle position), **links the board to the origin repo** (idempotent and non-fatal — Projects v2
boards are owned by a user/org, so linking is the only repo-level association there is; it surfaces
the board on the repo's Projects tab, but note it does **not** auto-add issues), and writes the
**committed** config file `agentic-engineering.md` at the repo root with `github_project_owner`,
`github_project_number`, and the recorded **`github_project_forward_binding`** — identity and policy
in one write. This file must be committed (not `.local`) — fresh clones and worktree-isolated
subagents need to resolve the same board identity and binding.

> **If you chose `auto-add`,** bootstrap **scaffolds** `.github/workflows/add-to-project.yml`
> (SHA-pinned `actions/add-to-project`, `permissions: {}`) and a `.github/dependabot.yml` to keep the
> pin fresh — commit both. The **one remaining manual step** is providing the workflow's token, which
> `GITHUB_TOKEN` cannot be (it can't write user/org Projects v2). Add a repo Actions secret
> **`ADD_TO_PROJECT_PAT`**, least-privilege first:
> - **Fine-grained PAT (recommended):** org **Projects: Read & write** + repo **Issues: Read-only** +
>   **Pull requests: Read-only** (for a user board, the account-level Projects R/W). Set an expiry and
>   rotate (~90d) — an expired token surfaces as a failing `add-to-project` run, not a doctor WARN.
> - **GitHub App installation token:** the hardened option for orgs (short-lived, revocable).
> - **Classic PAT (fallback):** `project` scope (+ `repo` for private) — account-wide; avoid unless
>   fine-grained PATs are unavailable.
>
> `/lifecycle-doctor`'s `board_forward_binding` check goes WARN→PASS once the workflow file exists
> (the secret itself is write-only and unverifiable from the CLI).

**(B) Backfill — put EXISTING issues on the board now.** This is **independent** of (A): auto-add
never backfills, so even with auto-add a board is never guaranteed to reflect the full repo, and a
workflow-only/manual repo may still have a pile of pre-existing issues to track. Offer it regardless
of the (A) choice:

```
question: "Add the repo's existing open issues to the board now? (one-time, idempotent)"
header: "Backfill"
options:
  - label: "Yes, backfill now"
    description: "Adds every open issue not already on the board. Safe to re-run."
  - label: "Skip"
    description: "Leave existing issues off the board; re-run later when new un-added issues exist."
```

If yes:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/lifecycle_board.py" --backfill
```

It reports `{added, already_present, failed}` counts and records a high-water mark
(`github_project_backfilled_through`), so a re-run adds only what a partial run missed. Enumerates
open issues only (closed issues and PRs are excluded), paginated — no silent cap.

One step still has no API and stays manual:

- **Ready-work saved view** — create a saved view filtered to `status:planned no:assignee`, sorted
  by Priority. Note it over-shows blocked items (the view has no way to filter on blocked-by), so
  check an item's Blocked-by field before starting work on it.

After bootstrapping, run `/lifecycle-doctor` to verify the board schema, automations, forward
binding, and config all resolve correctly before relying on it.

### Forking or cloning under a different owner — re-bootstrap

`agentic-engineering.md` is committed, so it travels with the repo — and it names **one specific
board** (`github_project_owner` / `github_project_number`). A Projects v2 board is owned by a
user/org and cannot be co-owned, so a fork or clone under a **different** owner inherits a config
that points at *someone else's* board. Left unfixed, lifecycle writes would target — or fail
against — the upstream board, not yours.

When adopting the plugin in a forked/cloned repo under a new owner, **re-run the bootstrap**:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/bootstrap_lifecycle_board.py"
```

Because no board yet exists under the new origin owner, the script creates a fresh one, links it to
your repo, and rewrites the `github_project_*` keys in place — preserving all other file content
**and your recorded `github_project_forward_binding`** (omit `--forward-binding` on the re-run to
keep it; pass it to change). Commit that change. `/lifecycle-doctor` confirms it: the
`board_repo_link` check WARNs when the configured board is not linked to your origin repo, and the
`board_forward_binding` check verifies the recorded forward choice, which together are the tell that
the committed config still points upstream.

## Step 3.7: Install the operating-principles always-on layer

The `operating-principles` skill ships a thin always-on layer — ten compressed execution rules plus
a trigger line that pulls the full skill in for multi-step work — as a paste-ready block at
`${CLAUDE_PLUGIN_ROOT}/skills/operating-principles/assets/claude-md-snippet.md`. Offer to install it
into the repo's agent instruction files.

Detect targets: `CLAUDE.md` and `AGENTS.md` at the repo root. A file already containing the marker
string `operating-principles always-on layer` has the block — skip it. If every existing target
already has the marker, skip this whole step silently (idempotent re-runs).

If at least one existing target lacks the marker, use AskUserQuestion:

```
question: "Install the operating-principles always-on layer into {files lacking it}?"
header: "Always-on"
options:
  - label: "Yes, install (Recommended)"
    description: "Appends ten compressed execution rules + a trigger line that loads the full skill for multi-step work."
  - label: "Skip"
    description: "Leave {files} untouched. Re-run this setup anytime to install."
```

If neither `CLAUDE.md` nor `AGENTS.md` exists, offer instead:

```
question: "No CLAUDE.md or AGENTS.md found. Create CLAUDE.md with the operating-principles layer?"
header: "Always-on"
options:
  - label: "Create CLAUDE.md"
    description: "New file containing just the always-on block."
  - label: "Skip"
    description: "Leave the repo without agent instruction files."
```

On yes, append the block — the marker grep makes this idempotent and symlink-safe (when `AGENTS.md`
links to `CLAUDE.md`, the second pass sees the marker the first pass just wrote and skips):

```bash
SNIPPET="${CLAUDE_PLUGIN_ROOT}/skills/operating-principles/assets/claude-md-snippet.md"
for f in CLAUDE.md AGENTS.md; do
  [ -f "$f" ] || continue                                          # existing files only
  grep -q "operating-principles always-on layer" "$f" && continue  # already installed
  printf '\n' >> "$f"
  cat "$SNIPPET" >> "$f"
done
```

For the create branch: `cat "$SNIPPET" > CLAUDE.md`.

The ten rules are tool-agnostic; in `AGENTS.md` the trigger line's skill reference is inert for
non-Claude tools while the rules themselves still apply as instructions.

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
Always-on:     {operating-principles layer: installed into <files> | already present | skipped}

Tip: Edit the "Review Context" section to add project-specific instructions.
     Change issue_tracker: in the frontmatter to switch trackers (github-project, github, none).
     Re-run this setup anytime to reconfigure.
     Run /lifecycle-doctor anytime to verify the lifecycle board is wired correctly.
```
