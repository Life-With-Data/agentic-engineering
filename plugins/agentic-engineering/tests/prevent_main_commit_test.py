"""Regression tests for ``scripts/prevent-main-commit.py``.

This PreToolUse/Bash hook keeps work on feature branches: it blocks a
``git commit`` while the current branch is ``main``/``master``, and blocks an
explicit ``git push`` whose refspec targets ``main``/``master`` (regardless of
the current branch). Everything else — feature-branch commits/pushes, unrelated
commands, branches merely *named* like ``main-feature`` — must pass through.

Because the hook reads the live branch via ``git branch --show-current``, the
tests drive it as a subprocess inside throwaway git repos whose branch we
control. Exit code 2 blocks; exit code 0 allows.

Run with: ``python3 -m unittest tests.prevent_main_commit_test``.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "prevent-main-commit.py"

BLOCK = 2
ALLOW = 0


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    )


def _run(command: str, cwd: Path, tool_name: str = "Bash") -> subprocess.CompletedProcess[str]:
    payload = {"tool_name": tool_name, "tool_input": {"command": command}}
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=str(cwd),
        timeout=10,
    )


class PreventMainCommitTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name)
        _git(self.repo, "init")
        # Identity is required for some git operations in CI containers.
        _git(self.repo, "config", "user.email", "test@example.com")
        _git(self.repo, "config", "user.name", "Test")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _on_branch(self, name: str) -> None:
        _git(self.repo, "checkout", "-b", name)

    # --- commit while on a protected branch: MUST block ------------------

    def test_blocks_commit_on_main(self) -> None:
        self._on_branch("main")
        result = _run('git commit -m "wip"', self.repo)
        self.assertEqual(result.returncode, BLOCK)
        self.assertIn("BLOCKED", result.stderr)

    def test_blocks_commit_on_master(self) -> None:
        self._on_branch("master")
        self.assertEqual(_run('git commit -m "wip"', self.repo).returncode, BLOCK)

    # --- explicit push to a protected branch: MUST block -----------------

    def test_blocks_push_to_main_from_feature_branch(self) -> None:
        self._on_branch("feature/x")
        self.assertEqual(_run("git push origin main", self.repo).returncode, BLOCK)

    def test_blocks_push_head_to_main(self) -> None:
        self._on_branch("feature/x")
        self.assertEqual(_run("git push origin HEAD:main", self.repo).returncode, BLOCK)

    # --- feature-branch work: MUST allow ---------------------------------

    def test_allows_commit_on_feature_branch(self) -> None:
        self._on_branch("feature/awesome")
        self.assertEqual(_run('git commit -m "wip"', self.repo).returncode, ALLOW)

    def test_allows_push_of_feature_branch(self) -> None:
        self._on_branch("feature/awesome")
        self.assertEqual(
            _run("git push -u origin feature/awesome", self.repo).returncode, ALLOW
        )

    def test_allows_branch_named_like_main(self) -> None:
        # `main-feature` is not `main` — the refspec regex must not over-match.
        self._on_branch("feature/x")
        self.assertEqual(_run("git push origin main-feature", self.repo).returncode, ALLOW)

    def test_commit_message_mentioning_main_does_not_trigger(self) -> None:
        self._on_branch("feature/x")
        self.assertEqual(
            _run('git commit -m "merge main into this branch later"', self.repo).returncode,
            ALLOW,
        )

    # --- `main` token in a SIBLING segment of a compound command ---------
    # The refspec check is scoped per `git push` segment, so a `main` in an
    # unrelated chained command must not be attributed to the push.

    def test_allows_feature_push_then_gh_pr_base_main(self) -> None:
        self._on_branch("feature/x")
        self.assertEqual(
            _run(
                "git push -u origin feature/x && gh pr create --base main",
                self.repo,
            ).returncode,
            ALLOW,
        )

    def test_allows_gh_pr_create_base_main_without_push(self) -> None:
        self._on_branch("feature/x")
        self.assertEqual(
            _run("gh pr create --base main --head feature/x", self.repo).returncode,
            ALLOW,
        )

    def test_allows_feature_push_piped_to_tail(self) -> None:
        self._on_branch("feature/x")
        self.assertEqual(
            _run("git push -u origin feature/x 2>&1 | tail -3", self.repo).returncode,
            ALLOW,
        )

    def test_blocks_real_main_push_chained_before_gh(self) -> None:
        # A genuine bypass in the first segment still fires despite a later gh cmd.
        self._on_branch("feature/x")
        self.assertEqual(
            _run("git push origin main && gh pr create", self.repo).returncode, BLOCK
        )

    # --- unrelated commands: MUST allow ----------------------------------

    def test_allows_status(self) -> None:
        self._on_branch("main")
        self.assertEqual(_run("git status", self.repo).returncode, ALLOW)

    def test_ignores_non_bash_tools(self) -> None:
        self._on_branch("main")
        self.assertEqual(
            _run('git commit -m "wip"', self.repo, tool_name="Read").returncode, ALLOW
        )


if __name__ == "__main__":
    unittest.main()
