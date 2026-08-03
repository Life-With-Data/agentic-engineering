"""Regression tests for ``scripts/prevent-main-commit.py``.

This PreToolUse/Bash hook keeps work on feature branches by blocking exactly one
thing: a ``git commit`` while the current branch is ``main``/``master``.
Everything else passes through — feature-branch commits, unrelated commands, and
**every** ``git push`` phrasing.

The hook deliberately does not police pushes. A client-side refspec check
decides from the shape of the phrasing rather than from what the push would do
(``git push`` from ``main`` updates remote ``main`` exactly as
``git push origin main`` does), and it blocks a required step of the delivery
lifecycle on forges without a PR flow. Push and force-push policy belongs on the
server. The push tests below therefore assert the *category* — no push phrasing
is blocked — generatively, so a reintroduced string check cannot silently pass
by dodging a frozen list of literals.

Because the hook reads the live branch via ``git branch --show-current``, the
tests drive it as a subprocess inside throwaway git repos whose branch we
control. Exit code 2 blocks; exit code 0 allows.

Run with: ``python3 -m unittest tests.prevent_main_commit_test``.
"""
from __future__ import annotations

import itertools
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "prevent-main-commit.py"

BLOCK = 2
ALLOW = 0

# Generative push corpus: every combination of flag × remote × refspec, plus the
# bare form and a few compound shapes. Generated rather than enumerated so the
# suite covers phrasings nobody thought to list.
PUSH_FLAGS = ("", "--force ", "--force-with-lease ", "-u ", "--no-verify ")
PUSH_REMOTES = ("", "origin ", "upstream ")
PUSH_REFSPECS = ("", "main", "master", "HEAD", "HEAD:main", "HEAD:refs/heads/main", "+main:main")

PUSH_COMMANDS = [
    f"git push {flag}{remote}{refspec}".strip()
    for flag, remote, refspec in itertools.product(PUSH_FLAGS, PUSH_REMOTES, PUSH_REFSPECS)
] + [
    "git push origin main && gh pr create",
    "git push origin main 2>&1 | tail -3",
    "git checkout main && git merge --no-ff feature/x && git push origin main",
]


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    )


def _run_payload(payload: dict, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=str(cwd),
        timeout=10,
    )


def _run(command: str, cwd: Path, tool_name: str = "Bash") -> subprocess.CompletedProcess[str]:
    return _run_payload(
        {"tool_name": tool_name, "tool_input": {"command": command}},
        cwd,
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

    def test_blocks_cursor_before_shell_execution_payload(self) -> None:
        self._on_branch("main")
        result = _run_payload({"command": 'git commit -m "wip"'}, self.repo)
        self.assertEqual(result.returncode, BLOCK)

    # --- pushes are never blocked, on any branch, in any phrasing --------

    def test_allows_every_push_phrasing_on_main(self) -> None:
        self._on_branch("main")
        for command in PUSH_COMMANDS:
            with self.subTest(command=command):
                self.assertEqual(_run(command, self.repo).returncode, ALLOW)

    def test_allows_every_push_phrasing_on_feature_branch(self) -> None:
        self._on_branch("feature/x")
        for command in PUSH_COMMANDS:
            with self.subTest(command=command):
                self.assertEqual(_run(command, self.repo).returncode, ALLOW)

    def test_push_rule_machinery_is_gone(self) -> None:
        # Structural guard: the helpers existed only to serve the push rule.
        source = SCRIPT.read_text()
        for symbol in ("pushes_to_protected", "SEGMENT_SPLIT", "split_segments"):
            with self.subTest(symbol=symbol):
                self.assertNotIn(symbol, source)

    # --- commits created by lifecycle operations on `main`: MUST allow ---
    # Merging into `main` is the delivery lifecycle, not a bypass.

    def test_allows_merge_and_friends_on_main(self) -> None:
        self._on_branch("main")
        for command in (
            "git merge --no-ff feature/x",
            "git cherry-pick abc1234",
            "git revert abc1234",
            "git am /tmp/patch.mbox",
        ):
            with self.subTest(command=command):
                self.assertEqual(_run(command, self.repo).returncode, ALLOW)

    # --- feature-branch work: MUST allow ---------------------------------

    def test_allows_commit_on_feature_branch(self) -> None:
        self._on_branch("feature/awesome")
        self.assertEqual(_run('git commit -m "wip"', self.repo).returncode, ALLOW)

    def test_commit_message_mentioning_main_does_not_trigger(self) -> None:
        self._on_branch("feature/x")
        self.assertEqual(
            _run('git commit -m "merge main into this branch later"', self.repo).returncode,
            ALLOW,
        )

    def test_quoted_mention_of_git_commit_does_not_trigger(self) -> None:
        # `strip_quotes` keeps prose that merely names the verb from firing.
        self._on_branch("main")
        self.assertEqual(
            _run('echo "run git commit on a branch instead"', self.repo).returncode,
            ALLOW,
        )

    # --- unrelated commands: MUST allow ----------------------------------

    def test_allows_status(self) -> None:
        self._on_branch("main")
        self.assertEqual(_run("git status", self.repo).returncode, ALLOW)

    def test_allows_gh_pr_create_base_main(self) -> None:
        self._on_branch("feature/x")
        self.assertEqual(
            _run("gh pr create --base main --head feature/x", self.repo).returncode,
            ALLOW,
        )

    def test_ignores_non_bash_tools(self) -> None:
        self._on_branch("main")
        self.assertEqual(
            _run('git commit -m "wip"', self.repo, tool_name="Read").returncode, ALLOW
        )


if __name__ == "__main__":
    unittest.main()
