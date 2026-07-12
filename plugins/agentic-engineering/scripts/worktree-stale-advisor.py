#!/usr/bin/env python3
"""
SessionStart advisory — NON-BLOCKING, non-destructive.

Completes the worktree-lifecycle story that the git-worktree skill's
`worktree-manager.sh gc` starts. `gc` reaps merged worktrees in the background
(at `git pull`/`git merge` time, or at the end of a swarm run), but nothing tells
a human who *opens or resumes a session inside* a worktree whose branch has
already merged. Such a worktree is dead — it will never receive further changes —
yet work continues on it, producing commits on a branch that's already gone.

This hook closes that gap: when a session starts inside `<repo>/.worktrees/<name>`
and that worktree's branch is fully merged into the base, it emits a one-line
advisory (via `additionalContext`) telling the agent to start fresh, and how to
remove the stale worktree. It never deletes anything (a SessionStart delete could
race a concurrent session) — the destructive reap stays in `gc`.

Cost is only paid inside a worktree: on the main tree the hook returns before any
network call. Silent unless the current worktree is genuinely stale.

Config: WORKTREE_GC_BASE overrides the base branch (shared with `gc`; default
origin/main, falling back to local main). Never blocks — only ever exits 0.
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys


def _git(cwd: str, args: "list[str]") -> str:
    result = subprocess.run(
        ["git", "-C", cwd, *args], text=True, capture_output=True
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def _resolve_base(cwd: str) -> str:
    base = os.environ.get("WORKTREE_GC_BASE", "").strip()
    if base:
        return base
    if _git(cwd, ["rev-parse", "--verify", "-q", "origin/main"]):
        return "origin/main"
    return "main"


def _main() -> int:
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        payload = {}

    cwd = payload.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()

    # Only meaningful inside a `.worktrees/<name>` worktree. `--git-common-dir`
    # points at the MAIN repo's .git even from a linked worktree, so its parent
    # is the main tree root regardless of where we're standing.
    common = _git(cwd, ["rev-parse", "--git-common-dir"])
    if not common:
        return 0
    common_path = pathlib.Path(common)
    if not common_path.is_absolute():
        common_path = (pathlib.Path(cwd) / common_path).resolve()
    main_root = common_path.parent
    worktrees_dir = main_root / ".worktrees"
    try:
        cwd_resolved = pathlib.Path(cwd).resolve()
    except OSError:
        return 0
    if worktrees_dir not in cwd_resolved.parents:
        return 0  # main tree or a non-plugin worktree layout — nothing to advise

    branch = _git(cwd, ["symbolic-ref", "--quiet", "--short", "HEAD"])
    if not branch:
        return 0  # detached HEAD — nothing to advise

    base = _resolve_base(cwd)
    if base.startswith("origin/"):
        subprocess.run(
            ["git", "-C", cwd, "fetch", "-q", "origin", base[len("origin/"):]],
            capture_output=True,
        )

    # Stale = every commit on the branch is patch-present in base (all '-', which
    # catches squash/rebase merges where SHAs differ) AND it had real commits.
    # Zero commits ahead (a fresh branch) or any '+' (unmerged work) → NOT stale.
    cherry = _git(cwd, ["cherry", base, branch])
    if not cherry:
        return 0
    lines = cherry.splitlines()
    ahead = sum(1 for ln in lines if ln.startswith("+"))
    merged = sum(1 for ln in lines if ln.startswith("-"))
    if ahead != 0 or merged < 1:
        return 0

    dirty = ""
    if _git(cwd, ["status", "--porcelain"]):
        dirty = " It has uncommitted changes — commit or discard them first."

    msg = (
        f"⚠ This worktree is on '{branch}', which is already merged into "
        f"{base} — it's stale and won't receive further changes.{dirty} Start "
        f"new work from a fresh session/worktree. To remove this one, from the "
        f'main tree run: git worktree remove "{cwd_resolved}" && '
        f'git branch -D "{branch}" — or run '
        f"`worktree-manager.sh gc` there to reap all merged worktrees at once."
    )

    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": msg,
        },
    }))
    return 0


def main() -> int:
    # Contract: this hook only ever exits 0. A stale-worktree advisory must
    # never fail a session start, whatever goes wrong underneath.
    try:
        return _main()
    except Exception:
        return 0


if __name__ == "__main__":
    sys.exit(main())
