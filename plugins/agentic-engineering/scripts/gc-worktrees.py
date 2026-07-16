#!/usr/bin/env python3
"""Garbage-collect merged Claude Code worktrees + their local branches.

Claude Code leaves `<repo>/.claude/worktrees/<name>` worktrees behind after their
branch merges: GitHub deletes the remote head branch, but the local worktree and
branch linger and accumulate. This sweeps them.

Designed to run from a git `post-merge` hook (fires on `git pull` / `git merge`),
and is equally safe to run by hand. It is DESTRUCTIVE, so — unlike the plugin's
always-on guard hooks — it is NOT auto-wired into any harness config. Install it
deliberately (see HOOKS.md).

A worktree + its branch are removed ONLY when ALL of these hold:
  - it lives under `<main>/.claude/worktrees/` (never the main tree or a hand-made
    worktree elsewhere),
  - it is not the worktree this process is running in,
  - its working tree is clean (no uncommitted changes),
  - it is fully merged: `git cherry <base> <branch>` shows zero '+' lines — every
    commit's patch is already in the base branch (this also catches rebase/squash
    merges, which change SHAs), AND at least one '-' (so a fresh, commit-less
    worktree is left alone),
  - it is not in active use: nothing outside node_modules/.git modified within the
    grace window (default 30 min), so a concurrent live session isn't yanked.

  WORKTREE_GC=0                 skip entirely
  WORKTREE_GC_GRACE_MIN=<n>     activity window in minutes (default 30)

Always exits 0 — never fails the surrounding git operation.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path


def _run(args: list[str], cwd: str | None = None, timeout: int = 30):
    try:
        p = subprocess.run(
            args, cwd=cwd, capture_output=True, text=True, timeout=timeout
        )
        return p.returncode, p.stdout.strip()
    except Exception:
        return 1, ""


def _default_branch(main_root: str) -> str:
    rc, ref = _run(
        ["git", "symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD"],
        cwd=main_root,
    )
    if rc == 0 and ref:
        return ref
    for cand in ("main", "master"):
        rc, _ = _run(
            ["git", "rev-parse", "--verify", "--quiet", f"origin/{cand}"],
            cwd=main_root,
        )
        if rc == 0:
            return f"origin/{cand}"
    return "origin/main"


def _recently_active(path: str, grace_min: int) -> bool:
    """True if any file outside node_modules/.git was modified within grace_min."""
    cutoff = time.time() - grace_min * 60
    root = Path(path)
    try:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in ("node_modules", ".git")]
            for name in filenames:
                try:
                    if (Path(dirpath) / name).stat().st_mtime >= cutoff:
                        return True
                except OSError:
                    continue
    except Exception:
        return True  # can't tell → assume active, keep the worktree
    return False


def _worktree_paths(main_root: str) -> list[str]:
    rc, out = _run(["git", "worktree", "list", "--porcelain"], cwd=main_root)
    if rc != 0:
        return []
    return [ln[len("worktree ") :] for ln in out.splitlines() if ln.startswith("worktree ")]


def main() -> int:
    if os.environ.get("WORKTREE_GC") == "0":
        return 0
    try:
        grace = int(os.environ.get("WORKTREE_GC_GRACE_MIN", "30"))
    except ValueError:
        grace = 30

    here = os.getcwd()
    rc, common = _run(["git", "rev-parse", "--git-common-dir"], cwd=here)
    if rc != 0 or not common:
        return 0
    common_path = Path(common)
    if not common_path.is_absolute():
        common_path = Path(here) / common_path
    try:
        main_root = str(common_path.parent.resolve())
    except Exception:
        return 0

    wt_dir = str(Path(main_root) / ".claude" / "worktrees")
    if not Path(wt_dir).is_dir():
        return 0

    base = _default_branch(main_root)
    _run(["git", "fetch", "-q", "origin", base.split("/", 1)[-1]], cwd=main_root)
    _run(["git", "remote", "prune", "origin"], cwd=main_root)

    here_abs = str(Path(here).resolve())
    removed = 0
    for path in _worktree_paths(main_root):
        try:
            path_abs = str(Path(path).resolve())
        except Exception:
            continue
        if not path_abs.startswith(wt_dir + os.sep):
            continue  # only Claude worktrees
        if path_abs == here_abs:
            continue  # never the one we're in
        rc, branch = _run(
            ["git", "symbolic-ref", "--quiet", "--short", "HEAD"], cwd=path_abs
        )
        if rc != 0 or not branch:
            continue  # detached → skip
        rc, dirty = _run(["git", "status", "--porcelain"], cwd=path_abs)
        if dirty:
            continue  # uncommitted work → skip
        rc, cherry = _run(["git", "cherry", base, branch], cwd=main_root)
        if rc != 0:
            continue
        lines = [ln for ln in cherry.splitlines() if ln.strip()]
        if any(ln.startswith("+") for ln in lines):
            continue  # unmerged/new work → skip
        if not any(ln.startswith("-") for ln in lines):
            continue  # fresh, commit-less worktree → skip
        if _recently_active(path_abs, grace):
            continue  # active session → skip
        rc, _ = _run(["git", "worktree", "remove", path_abs], cwd=main_root)
        if rc != 0:
            continue
        _run(["git", "branch", "-D", branch], cwd=main_root)
        removed += 1

    if removed:
        print(
            f"worktree-gc: removed {removed} merged worktree(s) + local branch(es).",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
