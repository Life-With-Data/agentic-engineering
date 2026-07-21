"""Tests for the `finish` and `sync` subcommands of ``worktree-manager.sh``.

Like ``worktree_session_test.py``, these build real throwaway git repos with
subprocess ``git`` and drive the script end-to-end. Each fixture uses a bare
file:// "origin" plus a "browser" clone that merges branches into main and
deletes the remote branch — the browser-merge shape whose local leftovers
`finish` and `sync` exist to clean up. Merge detection is TIERED by evidence
strength: squash merges (new sha) are tier "patch" via `git cherry`
patch-equivalence; merge commits (GitHub's default button — empty
`base..branch` range) are tier "merge-commit" via the merge-record scan;
fast-forward merges and brand-new commit-less branches are both tier
"ancestor-only" — genuinely indistinguishable in git, so that tier is gated
by the WORKTREE_GC_GRACE_MIN idle window (default 30m). Pinned invariants:

  - `finish` on an unambiguously merged branch (squash or merge-commit)
    removes the worktree, deletes the branch, and leaves the primary tree
    fast-forwarded on base, all without --force,
  - `finish` refuses an unmerged branch without --force and obeys --force,
  - `finish` refuses an ancestor-only branch (fast-forwarded OR fresh — it
    cannot tell which) without --force, with a message saying so,
  - `finish` rejects unknown --flags with a usage error,
  - `finish` resolves names under `.claude/worktrees/` and works when invoked
    from inside the target worktree,
  - `sync` reaps an unambiguously merged `.claude/worktrees/` tree with zero
    grace while leaving an unmerged sibling alone,
  - `sync` KEEPS a fresh commit-less worktree (and a fast-forward-merged one)
    within the grace window — printing the kept reason — and reaps it once
    past grace (WORKTREE_GC_GRACE_MIN=0 proves the reaping side); this pins
    the fix for one session's sync deleting a pristine worktree another
    session just created,
  - `sync` deletes a merged local branch whose worktree and upstream are gone,
    and keeps an unmerged one,
  - when the worktree DIRECTORY name differs from the checked-out BRANCH name
    (the harness-worktree shape), `finish <dirname>` and `sync` operate on the
    branch actually checked out in the worktree — a decoy local branch named
    after the directory is never touched.

Run with: ``python3 -m unittest tests.worktree_manager_test``.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = (
    Path(__file__).resolve().parent.parent
    / "skills"
    / "wf-development"
    / "scripts"
    / "worktree-manager.sh"
)


def _env(home=None):
    env = dict(os.environ)
    # Neutralize inherited git config (and HOME-based config) so the child
    # behaves deterministically regardless of the developer's machine.
    env["GIT_CONFIG_GLOBAL"] = "/dev/null"
    env["GIT_CONFIG_SYSTEM"] = "/dev/null"
    if home is not None:
        env["HOME"] = str(home)
    env.pop("WORKTREE_GC", None)
    env.pop("WORKTREE_GC_BASE", None)
    env.pop("WORKTREE_GC_GRACE_MIN", None)
    return env


def _git(cwd, *args):
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        env=_env(),
    )


class WorktreeManagerTest(unittest.TestCase):
    def _run(self, cwd, *args, extra_env=None):
        env = _env(home=self.tmp)
        if extra_env:
            env.update(extra_env)
        return subprocess.run(
            ["bash", str(SCRIPT), *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            env=env,
        )

    def _make_repo(self):
        """Bare origin + primary clone with an initial commit pushed to main."""
        self.tmp = Path(tempfile.mkdtemp()).resolve()
        self.origin = self.tmp / "origin.git"
        _git(self.tmp, "init", "-q", "--bare", "-b", "main", str(self.origin))
        self.primary = self.tmp / "primary"
        _git(self.tmp, "clone", "-q", str(self.origin), str(self.primary))
        _git(self.primary, "config", "user.email", "t@t")
        _git(self.primary, "config", "user.name", "t")
        (self.primary / "README.md").write_text("hi\n")
        _git(self.primary, "add", "-A")
        _git(self.primary, "commit", "-qm", "init")
        _git(self.primary, "push", "-qu", "origin", "main")
        return self.primary

    def _add_worktree(self, rel, branch, commit=True, push=True):
        """Linked worktree under the primary tree with one pushed commit."""
        wt = self.primary / rel
        wt.parent.mkdir(parents=True, exist_ok=True)
        _git(self.primary, "worktree", "add", "-q", "-b", branch, str(wt), "main")
        if commit:
            fname = branch.replace("/", "-") + ".txt"
            (wt / fname).write_text("work\n")
            _git(wt, "add", fname)
            _git(wt, "commit", "-qm", f"work on {branch}")
        if push:
            _git(wt, "push", "-qu", "origin", branch)
        return wt

    def _browser_squash_merge(self, branch, delete_remote=True):
        """Simulate merging the PR in the browser: a separate clone
        squash-merges <branch> into main (new sha), pushes, and deletes the
        remote branch."""
        merger = self.tmp / ("browser-" + branch.replace("/", "-"))
        _git(self.tmp, "clone", "-q", str(self.origin), str(merger))
        _git(merger, "config", "user.email", "b@b")
        _git(merger, "config", "user.name", "b")
        _git(merger, "merge", "--squash", "-q", f"origin/{branch}")
        _git(merger, "commit", "-qm", f"squash {branch}")
        _git(merger, "push", "-q", "origin", "main")
        if delete_remote:
            _git(merger, "push", "-q", "origin", "--delete", branch)

    def _browser_merge_commit(self, branch, delete_remote=True):
        """Simulate GitHub's default "Merge pull request" button: a separate
        clone merges <branch> into main with --no-ff (a merge commit — every
        branch commit stays reachable from main, so ``base..branch`` is
        EMPTY), pushes, and deletes the remote branch."""
        merger = self.tmp / ("browser-mc-" + branch.replace("/", "-"))
        _git(self.tmp, "clone", "-q", str(self.origin), str(merger))
        _git(merger, "config", "user.email", "b@b")
        _git(merger, "config", "user.name", "b")
        _git(merger, "merge", "--no-ff", "-q", "-m", f"Merge pull request from {branch}", f"origin/{branch}")
        _git(merger, "push", "-q", "origin", "main")
        if delete_remote:
            _git(merger, "push", "-q", "origin", "--delete", branch)

    def _browser_ff_merge(self, branch, delete_remote=True):
        """Simulate a fast-forward landing: a separate clone fast-forwards
        main onto <branch> (no new commit at all), pushes, and deletes the
        remote branch."""
        merger = self.tmp / ("browser-ff-" + branch.replace("/", "-"))
        _git(self.tmp, "clone", "-q", str(self.origin), str(merger))
        _git(merger, "config", "user.email", "b@b")
        _git(merger, "config", "user.name", "b")
        _git(merger, "merge", "--ff-only", "-q", f"origin/{branch}")
        _git(merger, "push", "-q", "origin", "main")
        if delete_remote:
            _git(merger, "push", "-q", "origin", "--delete", branch)

    def _branches(self):
        out = _git(
            self.primary, "for-each-ref", "--format=%(refname:short)", "refs/heads"
        ).stdout
        return set(out.split())

    def test_finish_merged_branch(self):
        self._make_repo()
        wt = self._add_worktree(".worktrees/login", "feat/login")
        self._browser_squash_merge("feat/login")
        r = self._run(self.primary, "finish", "login")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(wt.exists())
        self.assertNotIn("feat/login", self._branches())
        head_branch = _git(
            self.primary, "rev-parse", "--abbrev-ref", "HEAD"
        ).stdout.strip()
        self.assertEqual(head_branch, "main")
        # `git pull --ff-only` brought the squash commit into the primary tree.
        subject = _git(self.primary, "log", "-1", "--format=%s").stdout.strip()
        self.assertEqual(subject, "squash feat/login")

    def test_finish_refuses_unmerged_without_force(self):
        self._make_repo()
        wt = self._add_worktree(".worktrees/wip", "feat/wip", push=False)
        r = self._run(self.primary, "finish", "wip")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("not fully merged", r.stdout + r.stderr)
        self.assertTrue(wt.exists())
        self.assertIn("feat/wip", self._branches())
        # --force discards the unmerged work.
        r = self._run(self.primary, "finish", "wip", "--force")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(wt.exists())
        self.assertNotIn("feat/wip", self._branches())

    def test_finish_resolves_claude_worktrees_name(self):
        self._make_repo()
        wt = self._add_worktree(".claude/worktrees/sess", "claude/sess")
        self._browser_squash_merge("claude/sess")
        r = self._run(self.primary, "finish", "sess")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(wt.exists())
        self.assertNotIn("claude/sess", self._branches())

    def test_finish_from_inside_target_worktree(self):
        self._make_repo()
        wt = self._add_worktree(".claude/worktrees/inside", "claude/inside")
        self._browser_squash_merge("claude/inside")
        # Invoked from the doomed worktree itself: teardown must run from the
        # primary tree and still succeed.
        r = self._run(wt, "finish", "inside")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("inside the target worktree", r.stdout)
        self.assertFalse(wt.exists())
        self.assertNotIn("claude/inside", self._branches())

    def test_sync_reaps_merged_and_keeps_unmerged(self):
        self._make_repo()
        merged = self._add_worktree(".claude/worktrees/merged", "feat/merged")
        wip = self._add_worktree(".claude/worktrees/wip", "feat/wip", push=False)
        self._browser_squash_merge("feat/merged")
        # Files were modified seconds ago — zero grace must reap anyway.
        r = self._run(self.primary, "sync")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(merged.exists())
        self.assertNotIn("feat/merged", self._branches())
        self.assertTrue(wip.exists())
        self.assertIn("feat/wip", self._branches())
        self.assertIn("not fully merged", r.stdout)

    def test_sync_deletes_stale_merged_branch_with_gone_upstream(self):
        self._make_repo()
        old = self._add_worktree(".worktrees/old", "feat/old")
        keep = self._add_worktree(".worktrees/keep", "feat/keep")
        self._browser_squash_merge("feat/old")
        # feat/keep's remote branch is deleted WITHOUT being merged.
        _git(self.primary, "push", "-q", "origin", "--delete", "feat/keep")
        # Earlier manual cleanup removed the worktrees but left the branches.
        _git(self.primary, "worktree", "remove", str(old))
        _git(self.primary, "worktree", "remove", str(keep))
        r = self._run(self.primary, "sync")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("feat/old", self._branches())
        self.assertIn("feat/keep", self._branches())
        self.assertIn("feat/keep", r.stdout)  # reported as kept, with reason
        # Idempotent: a second sync changes nothing and still exits 0.
        r2 = self._run(self.primary, "sync")
        self.assertEqual(r2.returncode, 0, r2.stdout + r2.stderr)
        self.assertIn("feat/keep", self._branches())

    def test_finish_accepts_merge_commit_merge_without_force(self):
        """GitHub's default "Merge pull request" button leaves base..branch
        EMPTY; `git cherry` alone misclassifies that as unmerged. finish must
        accept it via the ancestry check, with no --force."""
        self._make_repo()
        wt = self._add_worktree(".worktrees/button", "feat/button")
        self._browser_merge_commit("feat/button")
        r = self._run(self.primary, "finish", "button")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(wt.exists())
        self.assertNotIn("feat/button", self._branches())

    def test_sync_reaps_merge_commit_merged_worktree(self):
        self._make_repo()
        merged = self._add_worktree(".claude/worktrees/mc", "feat/mc")
        self._browser_merge_commit("feat/mc")
        r = self._run(self.primary, "sync")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(merged.exists())
        self.assertNotIn("feat/mc", self._branches())

    def test_finish_refuses_fast_forward_merge_without_force(self):
        """A fast-forwarded branch leaves no unique commits and no merge
        record — tier ancestor-only, indistinguishable from a fresh branch.
        finish must refuse it without --force (naming the ambiguity) and
        proceed with --force."""
        self._make_repo()
        wt = self._add_worktree(".worktrees/ff", "feat/ff")
        self._browser_ff_merge("feat/ff")
        r = self._run(self.primary, "finish", "ff")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("no unique commits and no merge record", r.stdout + r.stderr)
        self.assertTrue(wt.exists())
        self.assertIn("feat/ff", self._branches())
        r = self._run(self.primary, "finish", "ff", "--force")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(wt.exists())
        self.assertNotIn("feat/ff", self._branches())

    def test_sync_fast_forward_merged_kept_within_grace_reaped_past_it(self):
        """Fast-forward-merged is tier ancestor-only: sync must keep it while
        it is younger than the grace window (files were touched seconds ago)
        and reap it once past grace (grace 0 disables the age gate)."""
        self._make_repo()
        merged = self._add_worktree(".claude/worktrees/ffs", "feat/ffs")
        self._browser_ff_merge("feat/ffs")
        r = self._run(self.primary, "sync")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(merged.exists())
        self.assertIn("feat/ffs", self._branches())
        self.assertIn("no merge evidence", r.stdout)
        self.assertIn("kept", r.stdout)
        r = self._run(self.primary, "sync", extra_env={"WORKTREE_GC_GRACE_MIN": "0"})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(merged.exists())
        self.assertNotIn("feat/ffs", self._branches())

    def test_sync_keeps_fresh_commitless_worktree_within_grace(self):
        """THE regression this change exists for: one session runs `sync`
        moments after another session created a pristine commit-less worktree.
        Its tip is an ancestor of base (tier ancestor-only), so it must
        survive with the kept-reason printed — and only be reaped once its
        last activity is older than the grace window (grace 0 here)."""
        self._make_repo()
        fresh = self._add_worktree(
            ".claude/worktrees/pristine", "claude/pristine", commit=False, push=False
        )
        r = self._run(self.primary, "sync")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(fresh.exists())
        self.assertIn("claude/pristine", self._branches())
        self.assertIn("no merge evidence", r.stdout)
        self.assertIn("kept", r.stdout)
        # Past the grace window the ambiguity resolves in favor of reaping.
        r = self._run(self.primary, "sync", extra_env={"WORKTREE_GC_GRACE_MIN": "0"})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(fresh.exists())
        self.assertNotIn("claude/pristine", self._branches())

    def test_sync_reaps_merged_immediately_and_keeps_fresh_sibling(self):
        """The exact user scenario: a merge-commit-merged worktree and a
        freshly created commit-less one, one sync, default grace. The merged
        tree must be reaped immediately (tier merge-commit — no grace) and
        the fresh one kept with the reason."""
        self._make_repo()
        merged = self._add_worktree(".claude/worktrees/landed", "feat/landed")
        fresh = self._add_worktree(
            ".claude/worktrees/newborn", "claude/newborn", commit=False, push=False
        )
        self._browser_merge_commit("feat/landed")
        r = self._run(self.primary, "sync")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(merged.exists())
        self.assertNotIn("feat/landed", self._branches())
        self.assertTrue(fresh.exists())
        self.assertIn("claude/newborn", self._branches())
        self.assertIn("no merge evidence", r.stdout)

    def test_finish_refuses_fresh_commitless_worktree_without_force(self):
        """finish on a brand-new commit-less worktree is ancestor-only: refuse
        without --force (it may simply not have been worked on yet), succeed
        with --force."""
        self._make_repo()
        wt = self._add_worktree(
            ".worktrees/blank", "feat/blank", commit=False, push=False
        )
        r = self._run(self.primary, "finish", "blank")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("no unique commits and no merge record", r.stdout + r.stderr)
        self.assertTrue(wt.exists())
        self.assertIn("feat/blank", self._branches())
        r = self._run(self.primary, "finish", "blank", "--force")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(wt.exists())
        self.assertNotIn("feat/blank", self._branches())

    def test_finish_rejects_unknown_flag(self):
        """An unknown --flag must be a usage error naming the flag, never
        silently consumed as the positional base branch."""
        self._make_repo()
        wt = self._add_worktree(".worktrees/flagged", "feat/flagged")
        r = self._run(self.primary, "finish", "flagged", "--bogus-flag")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("--bogus-flag", r.stdout + r.stderr)
        self.assertIn("Usage", r.stdout + r.stderr)
        self.assertTrue(wt.exists())
        self.assertIn("feat/flagged", self._branches())

    def test_finish_uses_checked_out_branch_not_dirname(self):
        """Harness worktrees routinely name the directory differently from the
        branch (dir `atomic-tumbling-owl`, branch `worktree-atomic-tumbling-owl`).
        finish <dirname> must act on the branch checked out IN the worktree; a
        decoy local branch named exactly after the directory must survive."""
        self._make_repo()
        wt = self._add_worktree(
            ".claude/worktrees/atomic-tumbling-owl", "worktree-atomic-tumbling-owl"
        )
        # Decoy: a local branch whose name equals the directory name. If the
        # script ever derived the branch to delete from the dirname, this is
        # the branch it would (wrongly) delete.
        _git(self.primary, "branch", "atomic-tumbling-owl", "main")
        self._browser_merge_commit("worktree-atomic-tumbling-owl")
        r = self._run(self.primary, "finish", "atomic-tumbling-owl")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(wt.exists())
        self.assertNotIn("worktree-atomic-tumbling-owl", self._branches())
        self.assertIn("atomic-tumbling-owl", self._branches())  # decoy untouched
        self.assertIn("worktree-atomic-tumbling-owl", r.stdout)  # reported branch is the real one

    def test_sync_uses_checked_out_branch_not_dirname(self):
        """sync's reap must likewise delete the branch checked out in the
        worktree, never one derived from the directory name."""
        self._make_repo()
        wt = self._add_worktree(
            ".claude/worktrees/sess-375de8", "claude/legacy-cleanup-375de8"
        )
        # Decoy, dir-named. It has no upstream, so the [gone]-branch pruning
        # cannot touch it; only a dirname-derived delete could.
        _git(self.primary, "branch", "sess-375de8", "main")
        self._browser_merge_commit("claude/legacy-cleanup-375de8")
        r = self._run(self.primary, "sync")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(wt.exists())
        self.assertNotIn("claude/legacy-cleanup-375de8", self._branches())
        self.assertIn("sess-375de8", self._branches())  # decoy untouched
        self.assertIn("claude/legacy-cleanup-375de8", r.stdout)


if __name__ == "__main__":
    unittest.main()
