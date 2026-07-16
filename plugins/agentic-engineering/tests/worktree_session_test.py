"""Tests for ``scripts/worktree-session.py``.

The SessionStart worktree hook is stdin/exit-code driven like the guard hooks,
but its interesting behavior only happens inside a *linked* worktree under
`<main>/.claude/worktrees/`. These tests build a real throwaway git repo + a
harness-shaped worktree with subprocess `git`, then drive the script end-to-end
to pin the load-bearing invariants:

  - fast no-op paths (env off, non-git dir, main tree) emit nothing, exit 0,
  - inside a `.claude/worktrees/*` tree it copies gitignored env files and, when
    the branch is merged into the default branch, appends a staleness advisory,
  - a fresh (commit-less) worktree is NOT reported stale.

Run with: ``python3 -m unittest tests.worktree_session_test``.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "worktree-session.py"

_spec = importlib.util.spec_from_file_location("worktree_session", SCRIPT)
worktree_session = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(worktree_session)


def _git(cwd, *args):
    subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )


def _run(cwd, extra_env=None):
    env = dict(os.environ)
    # Neutralize any inherited config so the child behaves deterministically.
    env.pop("AGENTIC_WORKTREE_BOOTSTRAP_CMD", None)
    env.pop("WORKTREE_BOOTSTRAP", None)
    env.pop("AGENTIC_WORKTREE_ENV_GLOBS", None)
    if extra_env:
        env.update(extra_env)
    payload = json.dumps({"cwd": cwd})
    return subprocess.run(
        ["python3", str(SCRIPT)],
        input=payload,
        capture_output=True,
        text=True,
        env=env,
    )


class WorktreeSessionTest(unittest.TestCase):
    def _make_repo(self):
        tmp = tempfile.mkdtemp()
        main = Path(tmp) / "repo"
        main.mkdir()
        _git(main, "init", "-q", "-b", "main")
        _git(main, "config", "user.email", "t@t")
        _git(main, "config", "user.name", "t")
        (main / "README.md").write_text("hi\n")
        _git(main, "add", "-A")
        _git(main, "commit", "-qm", "init")
        # A gitignored env file that git can't carry into a worktree.
        (main / ".env.local").write_text("SECRET=1\n")
        # Simulate a remote default branch so _default_branch resolves.
        _git(main, "update-ref", "refs/remotes/origin/main", "HEAD")
        return main

    def _add_worktree(self, main, name, branch):
        wt = main / ".claude" / "worktrees" / name
        wt.parent.mkdir(parents=True, exist_ok=True)
        _git(main, "worktree", "add", "-q", "-b", branch, str(wt), "main")
        return wt

    def test_bootstrap_disabled_is_noop(self):
        main = self._make_repo()
        r = _run(str(main), {"WORKTREE_BOOTSTRAP": "0"})
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout.strip(), "")

    def test_non_git_dir_is_noop(self):
        tmp = tempfile.mkdtemp()
        r = _run(tmp)
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout.strip(), "")

    def test_main_tree_is_noop(self):
        main = self._make_repo()
        r = _run(str(main))
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout.strip(), "")

    def test_worktree_copies_env_and_flags_missing_deps(self):
        main = self._make_repo()
        wt = self._add_worktree(main, "feat", "feature/x")
        self.assertFalse((wt / ".env.local").exists())
        r = _run(str(wt))
        self.assertEqual(r.returncode, 0)
        out = json.loads(r.stdout)
        ctx = out["hookSpecificOutput"]["additionalContext"]
        self.assertIn("env file", ctx)
        self.assertIn("AGENTIC_WORKTREE_BOOTSTRAP_CMD", ctx)
        self.assertEqual((wt / ".env.local").read_text(), "SECRET=1\n")

    def test_fresh_worktree_not_reported_stale(self):
        main = self._make_repo()
        wt = self._add_worktree(main, "fresh", "feature/fresh")
        r = _run(str(wt))
        self.assertEqual(r.returncode, 0)
        ctx = r.stdout
        self.assertNotIn("stale", ctx)

    def test_merged_worktree_reported_stale(self):
        main = self._make_repo()
        wt = self._add_worktree(main, "merged", "feature/merged")
        # Give the branch a commit, then land its patch on the default branch so
        # `git cherry` sees it as fully merged (all '-').
        (wt / "f.txt").write_text("x\n")
        _git(wt, "add", "f.txt")
        _git(wt, "commit", "-qm", "work")
        # Advance the default branch first so the landed patch gets a DIFFERENT sha
        # (a realistic squash/rebase merge), which is what `git cherry` detects.
        (main / "o.txt").write_text("other\n")
        _git(main, "add", "o.txt")
        _git(main, "commit", "-qm", "divergent")
        _git(main, "cherry-pick", "feature/merged")
        _git(main, "update-ref", "refs/remotes/origin/main", "HEAD")
        r = _run(str(wt))
        self.assertEqual(r.returncode, 0)
        out = json.loads(r.stdout)
        ctx = out["hookSpecificOutput"]["additionalContext"]
        self.assertIn("stale", ctx)


if __name__ == "__main__":
    unittest.main()
