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
4. It is fully merged into the base — `git cherry <base> <branch>` shows no `+` commits
   (patch-equivalence catches squash/rebase merges where SHAs differ); a brand-new empty
   branch (no commits) is left alone
5. It is idle — nothing outside `node_modules`/`.git` modified in the last grace window

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

### Companion note: the land-* skills defer teardown to `gc`

The land-* references — [`land-pr`](../../wf-delivery/references/land-pr.md) and
[`land-docs`](../../wf-documentation/references/land-docs.md) — are worktree-aware by design and **do not**
`git checkout <default>` from a linked worktree (the default branch is held by the primary tree, so
that checkout would fail). Instead they refresh `origin/<base>` with `git fetch` and **defer local
worktree + branch teardown to `gc`** rather than deleting inline. See land-pr's context-aware
post-merge cleanup (its step 6) for the canonical pattern.

Because teardown is deferred to `gc`, mind its two coverage limits (both from the rules above):
- **It cannot self-reap the active worktree.** `gc` skips the worktree it runs from and any worktree
  touched within the grace window (`WORKTREE_GC_GRACE_MIN`, default 30m) — so a skill landing *from* a
  worktree can never reap that same worktree in the same pass. It is reaped by a later `gc`, or by
  running `gc` from the primary tree.
- **It only reaps `$GIT_ROOT/.worktrees/`.** A worktree created elsewhere — e.g. a harness worktree
  under `.claude/worktrees/` — is outside `gc`'s scope and needs a manual
  `git worktree remove <path>` from the primary tree.

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
