---
name: setup
description: Configure which review agents run for your project. Auto-detects stack, writes agentic-engineering.local.md, and offers to bootstrap the lifecycle board, install the operating-principles always-on layer into CLAUDE.md/AGENTS.md, and install the Headroom context-compression CLI.
disable-model-invocation: true
---

# Agentic Engineering Setup

Interactive setup for `agentic-engineering.local.md` — configures which agents run during `/workflows:review` and `/workflows:work`.

## Step 1: Check Existing Config

Read `agentic-engineering.local.md` at the project root — the git toplevel (`git rev-parse
--show-toplevel`) when inside a git repository, the current directory otherwise. Step 4 writes to
the same location.

If the file exists, first run the full Step 4.5 recipe block now — the gitignore-ensure is
autonomous and idempotent, so running it early is safe. A copy committed before any `.gitignore`
entry existed stays tracked forever — an ignore entry alone never untracks an already-tracked
file — so when the recipe reports a tracked copy, present the warning and the untrack offer
exactly as Step 4.5 specifies (its consent gate and non-interactive rule apply unchanged), before
the menu, regardless of which option is chosen next. Then display current settings summary and
use AskUserQuestion:

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
>
> **Hardening:** the scaffolded workflow triggers on `issues: [opened]` only — do **not** add a
> `pull_request_target` trigger to it. That workflow holds a Projects-write PAT, and
> `pull_request_target` runs with secrets in scope against fork-controlled refs (the Pwn Request
> class). Keep it issue-triggered with no `run:` steps.

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

## Step 3.8: Install Headroom (optional)

The `headroom` skill wraps the [Headroom](https://github.com/headroomlabs-ai/headroom) CLI, which
compresses agent context (tool outputs, logs, RAG chunks, files) to cut 60-95% of tokens. The skill
installs it lazily on first invocation; this step offers to install it **up front** instead. It is
strictly opt-in — the plugin never installs a binary without consent.

First detect current state (idempotent — skip the offer entirely when already installed):

```bash
if command -v headroom >/dev/null 2>&1; then
  echo "state=installed version=$(headroom --version 2>/dev/null)"
elif command -v uv >/dev/null 2>&1; then
  echo "state=absent installer=uv"
elif command -v pip >/dev/null 2>&1 || command -v pip3 >/dev/null 2>&1; then
  echo "state=absent installer=pip"
else
  echo "state=absent installer=none"
fi
```

- If `state=installed`: skip this step silently.
- If `state=absent installer=none`: neither `uv` nor `pip` is available — do not offer an install
  that cannot run. State that installing Headroom needs `uv` (recommended) or `pip`, point at the
  skill for later, and move on.

Otherwise offer it with AskUserQuestion:

```
question: "Install Headroom now to compress agent context (60-95% fewer tokens)? It installs as a global CLI via {uv|pip}."
header: "Headroom"
options:
  - label: "Yes, install"
    description: "Runs {uv tool install|pip install} \"headroom-ai[all]\" now, then verifies with headroom doctor."
  - label: "Skip (Recommended)"
    description: "Leave it uninstalled — the headroom skill installs it on demand the first time it runs."
```

On yes, install with the detected installer (prefer `uv` — it isolates the CLI while exposing
`headroom` on PATH), then verify routing:

```bash
if command -v uv >/dev/null 2>&1; then
  uv tool install "headroom-ai[all]"
else
  (command -v pip3 >/dev/null 2>&1 && pip3 || echo pip) install "headroom-ai[all]"
fi
command -v headroom >/dev/null 2>&1 && headroom doctor
```

On non-interactive runs (no answer obtainable), never auto-install: print the `uv tool install
"headroom-ai[all]"` command for later and move on. Record the outcome for Step 5.

The `[all]` extra pulls optional ONNX features that need an AVX2-capable x86/x86_64 CPU; on other
architectures (e.g. Apple Silicon without Rosetta) the install may warn or fail on those extras —
fall back to the base package `headroom-ai` (no `[all]`), which the skill also documents.

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

## Step 4.5: Protect the Local Config

`agentic-engineering.local.md` is per-machine config and must never be committed: the lifecycle
runtime (`scripts/lifecycle_board.py`) ignores a *tracked* copy as a security invariant — a tracked
file rides PRs, and a PR must not be able to carry board identity or overrides — and prints a
stderr warning on every invocation until the file is untracked. Guard against that at write time:

```bash
ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || ROOT=""
if [ -n "$ROOT" ]; then
  # 1. Ensure a .gitignore entry (autonomous; always BEFORE any untrack offer,
  #    so a later `git add -A` cannot immediately re-track the file).
  if [ -L "$ROOT/.gitignore" ]; then
    GITIGNORE="failed"   # symlinked .gitignore — refuse to modify (see note below)
  elif git -C "$ROOT" check-ignore -q --no-index agentic-engineering.local.md; then
    GITIGNORE="entry present"
  else
    [ -s "$ROOT/.gitignore" ] && [ -n "$(tail -c1 "$ROOT/.gitignore")" ] && printf '\n' >> "$ROOT/.gitignore"
    printf 'agentic-engineering.local.md\n' >> "$ROOT/.gitignore"
    # Re-verify so "added" is never claimed when the append did not take effect.
    git -C "$ROOT" check-ignore -q --no-index agentic-engineering.local.md && GITIGNORE="added" || GITIGNORE="failed"
  fi
  # 2. Already tracked? (index check — the same command the runtime's _is_tracked uses)
  git -C "$ROOT" ls-files --error-unmatch agentic-engineering.local.md >/dev/null 2>&1 && TRACKED=1 || TRACKED=0
fi
echo "root=${ROOT:-none} gitignore=${GITIGNORE:-n/a} tracked=${TRACKED:-n/a}"
```

Recipe notes:

- A symlinked `.gitignore` is refused — git itself will not read one, and an autonomous append
  must never write through a link to a file outside the repo. The tracked-check and the config
  write still proceed; the status line reports `gitignore=failed`.
- `git check-ignore -q --no-index` is the idempotence gate — it honors broader patterns
  (`*.local.md`) and other ignore sources that an exact-line grep would misread; a manual
  `!agentic-engineering.local.md` negation reads as not-ignored, so the append proceeds and
  re-ignores the file — protect-by-default wins. No duplicate entries. `--no-index` is
  load-bearing: without it, a still-tracked file is *never* reported as ignored (tracked files
  aren't subject to exclude rules), so every re-run of setup against a legacy tracked copy would
  append the entry again.
- Append the exact literal line `agentic-engineering.local.md`, never a glob — the committed board
  config `agentic-engineering.md` (Step 3.6) differs by one token and must never be ignored.
- The `tail -c1` guard repairs a missing trailing newline so the append cannot corrupt the last
  existing pattern. The append creates `.gitignore` when absent; a new or changed `.gitignore` is
  itself a tracked change to commit.
- Outside a git repository the recipe is inert (the status line reports `root=none`) — the config
  write above stands.

Shell variables do not survive the tool call, so the final `echo` is the recipe's only observable
output — the consent gate below and Step 5's `Gitignore:`/`Tracked:` lines all derive from that
status line. If the status line reports `tracked=1` — and Step 1 of this run has not already
presented this offer — warn and offer to untrack (consent-gated — untracking mutates the index;
the file itself stays on disk):

```
question: "agentic-engineering.local.md is tracked in git. The lifecycle runtime ignores a tracked copy (it would ride PRs) and warns on every run until it is untracked. Untrack it now?"
header: "Untrack"
options:
  - label: "Yes, untrack (Recommended)"
    description: "git rm --cached agentic-engineering.local.md — keeps the file on disk, stages the deletion."
  - label: "No, leave tracked"
    description: "Setup completes; the warning repeats on every run until untracked."
```

- On yes: from the root reported on the status line, run
  `git rm --cached agentic-engineering.local.md` (with `--cached` it never touches the working
  file). Then state plainly: the deletion is now **staged** — commit it, ideally together with the
  `.gitignore` change, or the file still ships in PRs from HEAD. A tracked copy is shared across
  every clone — it may even be someone else's committed config inherited with the clone — so
  untracking affects only this clone's index until committed, and collaborators who pull that
  commit have their unmodified working copies deleted and re-run this setup to regenerate their
  own.
- On no — or whenever no answer is obtainable (non-interactive runs must never auto-run
  `git rm`) — print the exact command for later and move on; setup still completes:
  `git rm --cached agentic-engineering.local.md`.

## Step 5: Confirm

```
Saved to agentic-engineering.local.md

Stack:         {type}
Issue tracker: {tracker}    # github-project, github, or none
Review depth:  {depth}
Agents:        {count} configured
               {agent list, one per line}
Always-on:     {operating-principles layer: installed into <files> | already present | skipped}
Headroom:      {installed now | already present | skipped | unavailable (needs uv or pip) | command printed (non-interactive)}
Gitignore:     {entry present | added | failed (see warning) | n/a (not a git repo)}
Tracked:       {no | untracked now (deletion staged — commit it) | still tracked (declined) | still tracked (no answer — command printed) | n/a (not a git repo)}

Tip: Edit the "Review Context" section to add project-specific instructions.
     Change issue_tracker: in the frontmatter to switch trackers (github-project, github, none).
     Re-run this setup anytime to reconfigure.
     Run /lifecycle-doctor anytime to verify the lifecycle board is wired correctly.
```
