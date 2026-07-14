"""Regression tests for ``scripts/block-db-push.py``.

This PreToolUse/Bash hook blocks ``prisma db push``, which mutates the database
without writing a migration and so drifts the schema away from the migration
history. Like the other regex guards in this plugin, the tricky part is
precision: it must fire on a real push (in its various wrapper forms) but stay
quiet when a command merely *mentions* the phrase (prose, comments, quoted
strings) or runs a legitimate migration command.

Contract: exit code 2 blocks the command; exit code 0 allows it.

Run with: ``python3 -m unittest tests.block_db_push_test``.
"""
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "block-db-push.py"

BLOCK = 2
ALLOW = 0


def _run_payload(payload: dict) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=10,
    )


def _run(command: str, tool_name: str = "Bash") -> subprocess.CompletedProcess[str]:
    return _run_payload({"tool_name": tool_name, "tool_input": {"command": command}})


class BlockDbPushTest(unittest.TestCase):
    def assert_blocked(self, command: str) -> None:
        result = _run(command)
        self.assertEqual(result.returncode, BLOCK, f"expected BLOCK for: {command}")

    def assert_allowed(self, command: str) -> None:
        result = _run(command)
        self.assertEqual(result.returncode, ALLOW, f"expected ALLOW for: {command}")

    # --- real pushes must be blocked, in every wrapper form ---

    def test_blocks_bare_prisma_db_push(self) -> None:
        self.assert_blocked("prisma db push")

    def test_blocks_npx_prisma_db_push(self) -> None:
        self.assert_blocked("npx prisma db push")

    def test_blocks_pnpm_prisma_db_push(self) -> None:
        self.assert_blocked("pnpm prisma db push")

    def test_blocks_with_flags(self) -> None:
        self.assert_blocked("npx prisma db push --accept-data-loss")

    def test_blocks_dotenv_wrapped(self) -> None:
        self.assert_blocked("dotenv -e .env -- npx prisma db push")

    def test_blocks_pnpm_filter_push_alias(self) -> None:
        self.assert_blocked("pnpm --filter @repo/database push")

    def test_blocks_pnpm_filter_prisma_push_alias(self) -> None:
        self.assert_blocked("pnpm --filter database prisma push")

    def test_blocks_in_chained_command(self) -> None:
        self.assert_blocked("cd packages/database && npx prisma db push")

    def test_blocks_cursor_before_shell_execution_payload(self) -> None:
        result = _run_payload({"command": "npx prisma db push"})
        self.assertEqual(result.returncode, BLOCK)

    # --- legitimate commands must be allowed ---

    def test_allows_migrate_dev(self) -> None:
        self.assert_allowed("prisma migrate dev --name add_users")

    def test_allows_migrate_deploy(self) -> None:
        self.assert_allowed("npx prisma migrate deploy")

    def test_allows_generate(self) -> None:
        self.assert_allowed("npx prisma generate")

    def test_allows_git_push(self) -> None:
        self.assert_allowed("git push origin feature")

    # --- prose / mentions must NOT false-trigger ---

    def test_allows_quoted_mention_in_commit_message(self) -> None:
        self.assert_allowed('git commit -m "explain why prisma db push is banned"')

    def test_allows_echoing_the_phrase(self) -> None:
        self.assert_allowed("echo 'never run prisma db push'")

    def test_allows_grep_for_the_phrase(self) -> None:
        self.assert_allowed("grep -r 'prisma db push' docs/")

    # --- non-Bash tools are ignored ---

    def test_ignores_non_bash_tool(self) -> None:
        result = _run("prisma db push", tool_name="Write")
        self.assertEqual(result.returncode, ALLOW)


if __name__ == "__main__":
    unittest.main()
