# Git Worktree Manager

This reference provides a unified interface for managing Git worktrees across your development workflow. Whether you're reviewing PRs in isolation or working on features in parallel, this reference handles all the complexity.

## What This Reference Does

- **Create worktrees** from main branch with clear branch names
- **List worktrees** with current status
- **Switch between worktrees** for parallel work
- **Clean up completed worktrees** automatically
- **Interactive confirmations** at each step
- **Automatic .gitignore management** for worktree directory
- **Automatic .env file copying** from main repo to new worktrees

## CRITICAL: Always Use the Manager Script

**NEVER call `git worktree add` directly.** Always use the `worktree-manager.sh` script.

The script handles critical setup that raw git commands don't:
1. Copies `.env`, `.env.local`, `.env.test`, etc. from main repo
2. Ensures `.worktrees` is in `.gitignore`
3. Creates consistent directory structure

```bash
# ✅ CORRECT - Always use the script
bash <skill-directory>/scripts/worktree-manager.sh create feature-name

# ❌ WRONG - Never do this directly
git worktree add .worktrees/feature-name -b feature-name main
```

## When to Use This Reference

Use this reference in these scenarios:

1. **Code Review (the `wf-review` comprehensive-review route)**: If NOT already on the target branch (PR branch or requested branch), offer worktree for isolated review
2. **Feature Work (the `wf-development` work route)**: Always ask if user wants parallel worktree or live branch work
3. **Parallel Development**: When working on multiple features simultaneously
4. **Cleanup**: After completing work in a worktree

## How to Use

### In workflow routes

The `wf-development` work route loads this reference when isolation is needed.
The `wf-review` router may separately offer an isolated checkout before review.

```
# For review: offers worktree if not on PR branch
# For work: always asks - new branch or worktree?
```

### Manual Usage

You can also invoke the reference directly from bash:

```bash
# Create a new worktree (copies .env files automatically)
bash <skill-directory>/scripts/worktree-manager.sh create feature-login

# List all worktrees
bash <skill-directory>/scripts/worktree-manager.sh list

# Switch to a worktree
bash <skill-directory>/scripts/worktree-manager.sh switch feature-login

# Copy .env files to an existing worktree (if they weren't copied)
bash <skill-directory>/scripts/worktree-manager.sh copy-env feature-login

# Clean up completed worktrees
bash <skill-directory>/scripts/worktree-manager.sh cleanup

# Done with one branch: verify it merged, then remove worktree + branch
bash <skill-directory>/scripts/worktree-manager.sh finish feature-login

# Just merged a PR in the browser: reap everything merged, in both roots
bash <skill-directory>/scripts/worktree-manager.sh sync
```

## Commands

### `create <branch-name> [from-branch]`

Creates a new worktree with the given branch name.

**Options:**
- `branch-name` (required): The name for the new branch and worktree
- `from-branch` (optional): Base branch to create from (defaults to `main`)

**Example:**
```bash
bash <skill-directory>/scripts/worktree-manager.sh create feature-login
```

**What happens:**
1. Checks if worktree already exists
2. Updates the base branch from remote
3. Creates new worktree and branch
4. **Copies all .env files from main repo** (.env, .env.local, .env.test, etc.)
5. Shows path for cd-ing to the worktree

### `list` or `ls`

Lists all available worktrees with their branches and current status.

**Example:**
```bash
bash <skill-directory>/scripts/worktree-manager.sh list
```

**Output shows:**
- Worktree name
- Branch name
- Which is current (marked with ✓)
- Main repo status

### `switch <name>` or `go <name>`

Switches to an existing worktree and cd's into it.

**Example:**
```bash
bash <skill-directory>/scripts/worktree-manager.sh switch feature-login
```

**Optional:**
- If name not provided, lists available worktrees and prompts for selection

### `cleanup` or `clean`

Interactively cleans up inactive worktrees with confirmation.

**Example:**
```bash
bash <skill-directory>/scripts/worktree-manager.sh cleanup
```

**What happens:**
1. Lists all inactive worktrees
2. Asks for confirmation
3. Removes selected worktrees
4. Cleans up empty directories

> **Warning:** `cleanup` force-removes EVERY inactive worktree regardless of merge status,
> so it can discard unmerged parallel work. For unattended runs, prefer `gc`.

### `gc` (safe, non-interactive reap of merged worktrees)

Reaps only worktrees that are safe to drop — no prompts — so it can run at the end of a
parallel/swarm session or from a git `post-merge` hook. A worktree is reaped only when it is
fully merged into the base branch, has a clean tree, and has been idle for the grace window;
the orphaned local branch is deleted too.

**Example:**
```bash
bash <skill-directory>/scripts/worktree-manager.sh gc
bash <skill-directory>/scripts/worktree-manager.sh gc develop   # base = develop
```

**A worktree is reaped only when ALL hold:**
1. It lives under `.worktrees/` (never the main tree)
2. It is not the worktree `gc` is running from
3. Its working tree is clean (no uncommitted changes)
4. Its branch shows merge evidence, graded into three tiers:
   - **patch** — `git cherry <base> <branch>` shows every branch commit's patch already in
     the base under a different sha (squash/rebase merges). Unambiguous.
   - **merge-commit** — the branch tip is recorded as the merged-in (non-first) parent of a
     merge commit reachable from the base (GitHub's default "Merge pull request" button,
     where `base..branch` is empty). Unambiguous.
   - **ancestor-only** — the tip is an ancestor of the base with no unique commits and no
     merge record: a fast-forward merge OR a brand-new commit-less branch. Git genuinely
     cannot tell these apart, so this tier is only ever reaped after the grace window of
     inactivity (see `sync` below); ancestry alone is never treated as sufficient evidence.
5. It is idle — nothing outside `node_modules`/`.git` modified in the last grace window
   (`gc` applies the grace window to every tier)

**Configuration (env vars):**
- `WORKTREE_GC=0` — skip GC entirely
- `WORKTREE_GC_GRACE_MIN` — idle window in minutes (default `30`)
- `WORKTREE_GC_BASE` — base branch when no argument is passed (default `origin/main`,
  falling back to local `main`)

**Wiring it into a git `post-merge` hook** (auto-reap at `git pull`/`git merge` time):
```bash
# .git/hooks/post-merge (substitute the resolved absolute skill directory)
#!/bin/sh
bash <absolute-skill-directory>/scripts/worktree-manager.sh gc
```
`gc` always exits 0, so it never fails the surrounding git operation.

### `finish <name-or-path> [base] [--force]` (single-target teardown)

The explicit "I am done with this branch" command. Verifies the branch landed, then tears
down the worktree and its local branch and leaves the primary tree on an updated base.

**Example:**
```bash
bash <skill-directory>/scripts/worktree-manager.sh finish feature-login
bash <skill-directory>/scripts/worktree-manager.sh finish sess-a1b2c3     # .claude/worktrees/ name
bash <skill-directory>/scripts/worktree-manager.sh finish feature-x --force  # discard unmerged work
```

**What happens:**
1. Resolves the target as a literal path, then `.worktrees/<name>`, then
   `.claude/worktrees/<name>` — harness-created session worktrees are covered. The primary
   checkout itself is never a valid target. The branch it verifies and deletes is always the
   branch **checked out in that worktree**, never one derived from the directory name (harness
   worktrees routinely differ, e.g. dir `atomic-tumbling-owl`, branch
   `worktree-atomic-tumbling-owl`).
2. Refuses a dirty tree — or a branch without **unambiguous** merge evidence — unless
   `--force` is given. Unambiguous means tier patch (`git cherry` patch-equivalence,
   catching squash/rebase merges) or tier merge-commit (the tip is the merged-in parent of a
   merge commit in the base — GitHub's default merge button). A branch on the ancestor-only
   tier — no unique commits, no merge record — is refused with a message naming the
   ambiguity: it is indistinguishable from a branch that was just created, so `finish` will
   not destroy it; if it truly landed via fast-forward, re-run with `--force`.
3. In the primary tree: checks out the base branch and `git pull --ff-only` (tolerates
   offline / no upstream).
4. Removes the worktree (`--force` only when `--force` was given) and deletes the local
   branch.

`finish` may be run from **inside the target worktree**: it detects this, runs the
destructive steps from the primary tree, and warns that the caller's shell cwd will be gone.

> **Terminal-action caveat (agent sessions):** when a session runs `finish` on the worktree it
> is currently inside, the session's own cwd is deleted — **any further command in that
> shell/session fails**. Make `finish` the **last** action of the session (report first, then
> finish, then nothing), or defer teardown by handing the human the ready-to-paste one-liner
> instead: `bun run worktrees:finish -- <name>` (agentic-engineering repo) or
> `npx github:Life-With-Data/agentic-engineering worktrees finish <name>` (consuming repos).
> Never describe deferred cleanup as a manual `git worktree remove`.

### `sync [base]` (post-merge sweep across BOTH roots)

The one-liner after merging a PR in the browser. Runs `git fetch --prune origin` (warns and
continues offline), then applies the `gc` reap to **both** `.worktrees/` and
`.claude/worktrees/`, with grace depending on the evidence tier:

- **patch / merge-commit** (squash-, rebase-, and merge-commit-merged): reaped with **zero
  grace** — an explicit invocation is explicit intent, so the idle gate is skipped while
  every other safety gate (clean tree, not the current worktree) still applies.
- **ancestor-only** (fast-forward-merged OR freshly created with no commits — git cannot
  tell which): reaped only once the worktree has been idle longer than
  `WORKTREE_GC_GRACE_MIN` minutes (default 30). Within the window `sync` keeps it and
  prints the reason (`no merge evidence ... younger than <N>m grace — kept`). This is what
  protects a pristine worktree one session just created from a `sync` running concurrently
  in another session.

Finally it deletes leftover local branches whose worktree is already gone, whose upstream is
gone (`[gone]`), and which show merge evidence — covering branches stranded by earlier
manual cleanups. (For these, the `[gone]` upstream is itself evidence: a fresh local-only
branch never has an upstream, so ancestor-only + `[gone]` deletes safely.) Idempotent; safe
to run from the primary tree at any time — the catch-all for any teardown a session
deferred.

**Example:**
```bash
bash <skill-directory>/scripts/worktree-manager.sh sync
bash <skill-directory>/scripts/worktree-manager.sh sync develop   # base = develop
```

### Companion note: the land-* skills defer teardown to `finish`/`sync`

The land-* references — [`land-pr`](../../wf-delivery/references/land-pr.md) and
[`land-docs`](../../wf-documentation/references/land-docs.md) — are worktree-aware by design and **do not**
`git checkout <default>` from a linked worktree (the default branch is held by the primary tree, so
that checkout would fail). Instead they refresh `origin/<base>` with `git fetch` and **defer local
worktree + branch teardown to `finish` (or `sync`) from the primary tree** rather than deleting
inline. See land-pr's context-aware post-merge cleanup (its step 7) for the canonical pattern.

Because teardown is deferred, mind these coverage notes:
- **The sweeps never self-reap the active worktree.** `gc` and `sync` skip the worktree they run
  from (`gc` additionally skips any worktree touched within the grace window,
  `WORKTREE_GC_GRACE_MIN`, default 30m; `sync` applies that same window to worktrees on the
  ambiguous ancestor-only tier) — so a sweep issued *from* a worktree can never reap that
  same worktree in the same pass. `finish <name>` on the current worktree DOES proceed, but only
  as a terminal action (see the caveat in the finish section: the cwd is deleted, nothing may run
  after it). Otherwise clean it up afterwards with `finish <name>` (or a later `gc`/`sync`) from
  the primary tree, or hand the human the one-liner (`bun run worktrees:finish -- <name>` /
  `npx github:Life-With-Data/agentic-engineering worktrees finish <name>`).
- **`gc` only reaps `$GIT_ROOT/.worktrees/`.** A worktree elsewhere — e.g. a harness worktree under
  `.claude/worktrees/` — is outside `gc`'s scope; use `finish <name>` (single target) or `sync`
  (sweep), both of which cover `.claude/worktrees/` too. Raw `git worktree remove` is no longer
  needed.

## Workflow Examples

### Code Review with Worktree

```bash
# Claude Code recognizes you're not on the PR branch
# Offers: "Use worktree for isolated review? (y/n)"

# You respond: yes
# Script runs (copies .env files automatically):
bash <skill-directory>/scripts/worktree-manager.sh create pr-123-feature-name

# You're now in isolated worktree for review with all env vars
cd .worktrees/pr-123-feature-name

# After review, return to main:
cd ../..
bash <skill-directory>/scripts/worktree-manager.sh cleanup
```

### Parallel Feature Development

```bash
# For first feature (copies .env files):
bash <skill-directory>/scripts/worktree-manager.sh create feature-login

# Later, start second feature (also copies .env files):
bash <skill-directory>/scripts/worktree-manager.sh create feature-notifications

# List what you have:
bash <skill-directory>/scripts/worktree-manager.sh list

# Switch between them as needed:
bash <skill-directory>/scripts/worktree-manager.sh switch feature-login

# Return to main and cleanup when done:
cd .
bash <skill-directory>/scripts/worktree-manager.sh cleanup
```

## Key Design Principles

### KISS (Keep It Simple, Stupid)

- **One manager script** handles all worktree operations
- **Simple commands** with sensible defaults
- **Interactive prompts** prevent accidental operations
- **Clear naming** using branch names directly

### Opinionated Defaults

- Worktrees always created from **main** (unless specified)
- Worktrees stored in **.worktrees/** directory
- Branch name becomes worktree name
- **.gitignore** automatically managed

### Safety First

- **Confirms before creating** worktrees
- **Confirms before cleanup** to prevent accidental removal
- **Won't remove current worktree**
- **Clear error messages** for issues

## Integration with Workflows

### the `wf-review` comprehensive-review route

Instead of always creating a worktree:

```
1. Check current branch
2. If ALREADY on target branch (PR branch or requested branch) → stay there, no worktree needed
3. If DIFFERENT branch than the review target → offer worktree:
   "Use worktree for isolated review? (y/n)"
   - yes → run the bundled worktree manager
   - no → proceed with PR diff on current branch
```

### the `wf-development` work route

Always offer choice:

```
1. Ask: "How do you want to work?
   1. New branch on current worktree (live work)
   2. Worktree (parallel work)"

2. If choice 1 → create new branch normally
3. If choice 2 → run the bundled worktree manager to create from the base branch
```

## Troubleshooting

### "Worktree already exists"

If you see this, the script will ask if you want to switch to it instead.

### "Cannot remove worktree: it is the current worktree"

Switch out of the worktree first (to main repo), then cleanup:

```bash
cd $(git rev-parse --show-toplevel)
bash <skill-directory>/scripts/worktree-manager.sh cleanup
```

### Lost in a worktree?

See where you are:

```bash
bash <skill-directory>/scripts/worktree-manager.sh list
```

### .env files missing in worktree?

If a worktree was created without .env files (e.g., via raw `git worktree add`), copy them:

```bash
bash <skill-directory>/scripts/worktree-manager.sh copy-env feature-name
```

Navigate back to main:

```bash
cd $(git rev-parse --show-toplevel)
```

## Technical Details

### Directory Structure

```
.worktrees/
├── feature-login/          # Worktree 1
│   ├── .git
│   ├── app/
│   └── ...
├── feature-notifications/  # Worktree 2
│   ├── .git
│   ├── app/
│   └── ...
└── ...

.gitignore (updated to include .worktrees)
```

### How It Works

- Uses `git worktree add` for isolated environments
- Each worktree has its own branch
- Changes in one worktree don't affect others
- Share git history with main repo
- Can push from any worktree

### Performance

- Worktrees are lightweight (just file system links)
- No repository duplication
- Shared git objects for efficiency
- Much faster than cloning or stashing/switching
