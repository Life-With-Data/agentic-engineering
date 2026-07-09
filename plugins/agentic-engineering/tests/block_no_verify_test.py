"""Regression tests for ``scripts/block-no-verify.py``.

This PreToolUse/Bash hook blocks ``git commit``/``git push`` that carry
``--no-verify`` (or the ``-n`` short form on commit), so quality gates can't be
silently skipped. It is a *regex* guard, and the tricky part is precision: it
must fire on a real bypass but stay quiet when a command merely *mentions* the
flag (prose, comments, quoted commit messages, unrelated verbs). The hook's own
docstring documents these edge cases as things the naive substring check got
wrong — these tests pin that behaviour so it can't regress.

Contract: exit code 2 blocks the command; exit code 0 allows it.

Run with: ``python3 -m unittest tests.block_no_verify_test``.
"""
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "block-no-verify.py"

BLOCK = 2
ALLOW = 0


def _run(command: str, tool_name: str = "Bash") -> subprocess.CompletedProcess[str]:
    payload = {"tool_name": tool_name, "tool_input": {"command": command}}
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=10,
    )


class BlockNoVerifyTest(unittest.TestCase):
    # --- true bypasses: MUST block ---------------------------------------

    def test_blocks_commit_long_flag(self) -> None:
        self.assertEqual(_run('git commit -m "wip" --no-verify').returncode, BLOCK)

    def test_blocks_commit_short_flag(self) -> None:
        self.assertEqual(_run("git commit -n -m wip").returncode, BLOCK)

    def test_blocks_push_no_verify(self) -> None:
        self.assertEqual(_run("git push --no-verify origin HEAD").returncode, BLOCK)

    def test_blocks_bypass_in_later_segment(self) -> None:
        # The bypass is the second segment's verb, not the first's.
        self.assertEqual(_run("echo hi && git commit --no-verify").returncode, BLOCK)

    def test_block_message_is_actionable(self) -> None:
        result = _run("git commit --no-verify")
        self.assertEqual(result.returncode, BLOCK)
        self.assertIn("BLOCKED", result.stderr)

    # --- false positives: MUST allow -------------------------------------

    def test_allows_clean_commit(self) -> None:
        self.assertEqual(_run('git commit -m "normal commit"').returncode, ALLOW)

    def test_allows_flag_inside_quoted_message(self) -> None:
        # Commit message that talks about the flag must not self-trigger.
        self.assertEqual(
            _run('git commit -m "document the --no-verify escape hatch"').returncode,
            ALLOW,
        )

    def test_allows_flag_in_shell_comment(self) -> None:
        self.assertEqual(
            _run("git commit -m wip  # never pass --no-verify here").returncode,
            ALLOW,
        )

    def test_allows_grep_mentioning_flag(self) -> None:
        self.assertEqual(_run("grep -- --no-verify .claude/hooks/*.py").returncode, ALLOW)

    def test_allows_echo_mentioning_flag(self) -> None:
        self.assertEqual(_run("echo 'always avoid --no-verify'").returncode, ALLOW)

    def test_does_not_cross_segment_boundary(self) -> None:
        # `commit` is in segment 1; the `--no-verify` is in a later segment
        # attached to a different verb, so this is NOT a commit bypass.
        self.assertEqual(_run("git commit -m ok && echo --no-verify").returncode, ALLOW)

    def test_ignores_non_bash_tools(self) -> None:
        self.assertEqual(
            _run("git commit --no-verify", tool_name="Read").returncode, ALLOW
        )

    # --- heredoc PR/issue bodies: MUST allow (data, not commands) ---------

    def test_allows_flag_in_heredoc_pr_body_quoted_delim(self) -> None:
        cmd = (
            "gh pr create --body-file - <<'EOF'\n"
            "We block git commit --no-verify in CI.\n"
            "EOF"
        )
        self.assertEqual(_run(cmd).returncode, ALLOW)

    def test_allows_flag_in_heredoc_pr_body_bare_delim(self) -> None:
        cmd = (
            "gh pr create --title x --body-file - <<EOF\n"
            "Run git commit --no-verify to skip.\n"
            "EOF"
        )
        self.assertEqual(_run(cmd).returncode, ALLOW)

    def test_allows_flag_in_dash_indented_heredoc(self) -> None:
        cmd = (
            "gh pr create --body-file - <<-EOF\n"
            "\tprose git commit --no-verify\n"
            "\tEOF"
        )
        self.assertEqual(_run(cmd).returncode, ALLOW)

    def test_blocks_real_bypass_after_heredoc_body(self) -> None:
        # Heredoc body is stripped, but a real bypass chained AFTER it still fires.
        cmd = (
            "gh pr create --body-file - <<EOF\n"
            "some body\n"
            "EOF\n"
            "git commit --no-verify"
        )
        self.assertEqual(_run(cmd).returncode, BLOCK)


if __name__ == "__main__":
    unittest.main()
