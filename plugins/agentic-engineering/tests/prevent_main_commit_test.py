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

# Generative push corpus: every combination of flag × remote × refspec, plus a
# few compound shapes. Generated rather than enumerated so the suite covers
# phrasings nobody thought to list.
#
# Both slots are deliberately wide, and the refspec slot is derived from the
# protected-branch names rather than frozen: a corpus that spells every
# qualified form for `main` but only the bare form for `master` is blind to a
# check keyed on `refs/heads/master`, and one missing `-f` is blind to the
# single most likely reintroduction of all. Mutation-tested — narrower versions
# of these tuples let real push-blocking checks pass the suite.
PROTECTED = ("main", "master")
PUSH_FLAGS = (
    "", "-f ", "--force ", "--force-with-lease ", "-u ",
    "--no-verify ", "--all ", "--mirror ", "--tags ",
)
PUSH_REMOTES = ("", "origin ")
PUSH_REFSPECS = ("", "HEAD") + tuple(
    template.format(b=b)
    for b in PROTECTED
    for template in (
        "{b}", "HEAD:{b}", "HEAD:refs/heads/{b}", "refs/heads/{b}",
        "+{b}:{b}", "--delete {b}",
    )
)

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


def _run(
    command: str,
    cwd: Path,
    tool_name: str = "Bash",
    payload_cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    payload: dict = {"tool_name": tool_name, "tool_input": {"command": command}}
    if payload_cwd is not None:
        payload["cwd"] = str(payload_cwd)
    return _run_payload(payload, cwd)


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

    def test_allows_push_to_protected_from_feature_branch(self) -> None:
        # The corpus above runs on `main` only: a push command early-allows
        # before the hook ever reads the branch, so running the full product on
        # a second branch pins nothing and doubles the runtime. This one case
        # pins that the branch genuinely does not matter for pushes.
        self._on_branch("feature/x")
        self.assertEqual(_run("git push origin main", self.repo).returncode, ALLOW)

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

    def test_allows_commit_on_branch_named_like_main(self) -> None:
        # `main-feature` is not `main`. The protected set is matched by equality,
        # not substring; nothing else in the suite pins that.
        self._on_branch("main-feature")
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


class CommitVerbParsingTest(unittest.TestCase):
    """Issue #364: git global options between `git` and `commit` must not hide
    the verb, and heredoc bodies must not fake it."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name)
        _git(self.repo, "init", "-b", "main")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_global_options_before_commit_still_block_on_main(self) -> None:
        # Generated: every flag-style and value-style global option git accepts
        # in front of a subcommand, so an unlisted spelling cannot slip through.
        flags = ("--no-pager", "--paginate", "--no-replace-objects", "--literal-pathspecs")
        valued = ("-c user.name=x", '-c user.name="a b"', "-C .", "--git-dir=.git", "--git-dir .git")
        for prefix in flags + valued + ("--no-pager -c user.name=x -C .",):
            command = f"git {prefix} commit -m wip"
            with self.subTest(command=command):
                self.assertEqual(_run(command, self.repo).returncode, BLOCK)

    def test_wrapped_and_env_prefixed_commit_blocks_on_main(self) -> None:
        for command in ("time git commit -m wip", "GIT_AUTHOR_NAME=x git commit -m wip"):
            with self.subTest(command=command):
                self.assertEqual(_run(command, self.repo).returncode, BLOCK)

    def test_commands_that_only_name_the_verb_allow_on_main(self) -> None:
        for command in (
            "git log --grep commit",
            "git help commit",
            "git config --get commit.template",
            "git -c user.name=x log --grep commit",
        ):
            with self.subTest(command=command):
                self.assertEqual(_run(command, self.repo).returncode, ALLOW)

    def test_heredoc_body_mentioning_commit_allows_on_main(self) -> None:
        command = "gh pr create --body-file - <<'EOF'\nthen git commit -m wip\nEOF"
        self.assertEqual(_run(command, self.repo).returncode, ALLOW)

    def test_commit_chained_after_heredoc_blocks_on_main(self) -> None:
        command = "gh pr create --body-file - <<'EOF'\nbody\nEOF\ngit commit -m wip"
        self.assertEqual(_run(command, self.repo).returncode, BLOCK)

    def test_commit_message_heredoc_blocks_on_main(self) -> None:
        command = "git commit -F - <<'EOF'\nfix: thing\nEOF"
        self.assertEqual(_run(command, self.repo).returncode, BLOCK)


class WorktreeTargetTest(unittest.TestCase):
    """The branch is read where the commit runs, not in the hook's own cwd.

    Claude Code starts hooks in the project root. With the main checkout on
    `main` and the session working in a linked worktree on a feature branch,
    reading the hook's cwd blocked every commit in the worktree.
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self.main = root / "main"
        self.wt = root / "wt"
        _git(root, "init", "-b", "main", str(self.main))
        _git(self.main, "-c", "user.name=t", "-c", "user.email=t@x", "commit", "--allow-empty", "-m", "init")
        _git(self.main, "worktree", "add", "-b", "feature/x", str(self.wt))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_payload_cwd_in_feature_worktree_allows(self) -> None:
        result = _run("git commit -m wip", self.main, payload_cwd=self.wt)
        self.assertEqual(result.returncode, ALLOW)

    def test_cd_into_feature_worktree_allows(self) -> None:
        for command in (
            f"cd {self.wt} && git add -A && git commit -m wip",
            f"cd {self.wt}; git commit -m wip",
            f"(cd {self.wt} && git commit -m wip)",
            f"cd {self.wt.parent} && cd wt && git commit -m wip",
        ):
            with self.subTest(command=command):
                result = _run(command, self.main, payload_cwd=self.main)
                self.assertEqual(result.returncode, ALLOW)

    def test_dash_c_to_feature_worktree_allows(self) -> None:
        result = _run(f"git -C {self.wt} commit -m wip", self.main, payload_cwd=self.main)
        self.assertEqual(result.returncode, ALLOW)

    def test_relative_dash_c_resolves_against_payload_cwd(self) -> None:
        result = _run("git -C wt commit -m wip", self.main, payload_cwd=self.wt.parent)
        self.assertEqual(result.returncode, ALLOW)

    def test_dash_c_to_main_checkout_from_worktree_blocks(self) -> None:
        result = _run(f"git -C {self.main} commit -m wip", self.wt, payload_cwd=self.wt)
        self.assertEqual(result.returncode, BLOCK)

    def test_cd_to_main_checkout_from_worktree_blocks(self) -> None:
        result = _run(f"cd {self.main} && git commit -m wip", self.wt, payload_cwd=self.wt)
        self.assertEqual(result.returncode, BLOCK)

    def test_worktree_on_main_blocks(self) -> None:
        _git(self.main, "checkout", "-b", "other")
        _git(self.wt, "checkout", "main")
        result = _run("git commit -m wip", self.main, payload_cwd=self.wt)
        self.assertEqual(result.returncode, BLOCK)

    def test_plain_checkout_on_main_without_payload_cwd_blocks(self) -> None:
        self.assertEqual(_run("git commit -m wip", self.main).returncode, BLOCK)

    def test_any_commit_on_main_in_a_chain_blocks(self) -> None:
        command = f"git -C {self.wt} commit -m a && git -C {self.main} commit -m b"
        self.assertEqual(_run(command, self.wt, payload_cwd=self.wt).returncode, BLOCK)


if __name__ == "__main__":
    unittest.main()
