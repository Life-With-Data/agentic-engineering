# Git Worktree Manager

Manage isolated worktrees for parallel work and isolated review through the
bundled manager script.

**Always use the manager script — never raw `git worktree add`.** The script
copies `.env*` files from the main repo, keeps `.worktrees/` gitignored, and
enforces a consistent layout:

```bash
bash <skill-directory>/scripts/worktree-manager.sh <command>
```

Two managed roots: `.worktrees/` (created by `create`) and `.claude/worktrees/`
(harness-created). Every teardown and navigation command covers both; a
worktree anywhere else needs `finish <path>` with an explicit path.

## When to use

- **Review**: already on the target branch → stay; on a different branch → in
  an interactive session, offer an isolated worktree (in autonomous runs,
  create one without asking when isolation is needed).
- **Work**: in an interactive session, ask branch-vs-worktree once; in
  autonomous runs, default to a worktree for parallel work and a plain branch
  otherwise.

## Commands

| Command | What it does |
|---|---|
| `create <branch> [from]` | New worktree + branch under `.worktrees/` (base defaults to `main`); updates base from remote, copies `.env*` files. Refuses a name that exists in either root. |
| `list` / `ls` | All worktrees in both roots, labeled, current marked. |
| `switch <name>` / `go` | cd into a worktree; ambiguous names (both roots) error. |
| `copy-env <name>` | Re-copy `.env*` files into an existing worktree. |
| `cleanup` | Interactive: force-removes EVERY inactive worktree **regardless of merge status** — can discard unmerged work. Prefer `gc`/`sync`/`finish`; never use in unattended runs. |
| `gc [base]` | Safe non-interactive reap of merged, clean, idle worktrees (+ their branches). Always exits 0 — safe in a `post-merge` hook. |
| `finish <name-or-path> [base] [--force]` | Single-target teardown: verify merged, remove worktree, delete branch, leave primary tree on updated base. |
| `sync [base]` | Post-merge sweep: fetch --prune, reap merged worktrees in both roots, delete stranded `[gone]`-upstream merged branches. Idempotent catch-all. |

### Merge evidence (what `gc`/`finish`/`sync` trust)

- **patch** — `git cherry` shows every branch commit's patch already in base
  (squash/rebase merges). Unambiguous.
- **merge-commit** — the tip is the merged-in parent of a merge commit in base
  (GitHub's default merge button). Unambiguous.
- **ancestor-only** — tip is an ancestor with no unique commits and no merge
  record: a fast-forward merge OR a brand-new branch — git cannot tell which.
  `finish` refuses it without `--force`; `gc`/`sync` reap it only after the
  idle grace window (`WORKTREE_GC_GRACE_MIN`, default 30m), which protects a
  pristine worktree another session just created. `sync` reaps the two
  unambiguous tiers with zero grace (explicit invocation is explicit intent).

`gc` env vars: `WORKTREE_GC=0` skips entirely; `WORKTREE_GC_BASE` sets the
default base (`origin/main`, falling back to local `main`).

### `finish` details

Resolves literal path → `.worktrees/<name>` → `.claude/worktrees/<name>`; the
branch verified and deleted is always the one **checked out in that worktree**,
never derived from the directory name (harness worktrees routinely differ).
Refuses a dirty tree or ambiguous merge evidence without `--force`. May run
from inside the target worktree — but then the session's cwd is deleted:

> **Terminal-action rule:** teardown is the session's job, never the user's.
> Make `finish` the LAST shell action of the session — report first, invoke
> the script by its primary-tree path, then nothing (the cwd dies with the
> worktree). Handing the user a cleanup one-liner
> (`bun run worktrees:finish -- <name>` /
> `npx github:Life-With-Data/agentic-engineering worktrees finish <name>`)
> is a failure handoff reserved for a host that cannot run another shell
> command, and must be reported as the teardown NOT having happened — never
> as a normal ending, and never as a manual `git worktree remove`.

### Land-* integration

[`land-pr`](../../wf-delivery/references/land-pr.md) and
[`land-docs`](../../wf-documentation/references/land-docs.md) never
`git checkout <default>` from a linked worktree (the primary tree holds it) —
they fetch `origin/<base>` and defer teardown to `finish`/`sync` from the
primary tree. The sweeps never self-reap the worktree they run from.

## Examples

```bash
# Isolated review
bash <skill-directory>/scripts/worktree-manager.sh create pr-123-feature-name
cd .worktrees/pr-123-feature-name
# ... review ...
cd ../..
bash <skill-directory>/scripts/worktree-manager.sh finish pr-123-feature-name

# Parallel features
bash <skill-directory>/scripts/worktree-manager.sh create feature-login
bash <skill-directory>/scripts/worktree-manager.sh create feature-notifications
bash <skill-directory>/scripts/worktree-manager.sh switch feature-login
# When one merges:
bash <skill-directory>/scripts/worktree-manager.sh finish feature-login
# Or reap everything already merged:
bash <skill-directory>/scripts/worktree-manager.sh sync
```
