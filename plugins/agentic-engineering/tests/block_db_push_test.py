"""Regression tests for ``scripts/block-db-push.py``.

This PreToolUse/Bash hook blocks ``prisma db push``, which mutates the schema
directly and desyncs the database from its migration history. Like the other
guards in this plugin it is a *regex* check, so the tricky part is precision: it
must fire on a real push across the many runner forms (``npx``/``pnpm``/``bunx``/
``yarn``/``dotenv`` prefixes) but stay quiet when a command merely *mentions* the
phrase (prose, comments, quoted strings) or runs the correct ``migrate`` verb.

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


def _run(command: str, tool_name: str = "Bash") -> subprocess.CompletedProcess[str]:
    payload = {"tool_name": tool_name, "tool_input": {"command": command}}
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=10,
    )


class BlockDbPushTest(unittest.TestCase):
    # --- real `prisma db push`, various runner forms: MUST block ---------

    def test_blocks_bare_prisma_db_push(self) -> None:
        result = _run("prisma db push")
        self.assertEqual(result.returncode, BLOCK)
        self.assertIn("BLOCKED", result.stderr)

    def test_blocks_npx_prisma_db_push(self) -> None:
        self.assertEqual(_run("npx prisma db push").returncode, BLOCK)

    def test_blocks_pnpm_prisma_db_push(self) -> None:
        self.assertEqual(_run("pnpm prisma db push").returncode, BLOCK)

    def test_blocks_bunx_prisma_db_push(self) -> None:
        self.assertEqual(_run("bunx prisma db push").returncode, BLOCK)

    def test_blocks_yarn_prisma_db_push(self) -> None:
        self.assertEqual(_run("yarn prisma db push").returncode, BLOCK)

    def test_blocks_db_push_with_flags(self) -> None:
        self.assertEqual(
            _run("npx prisma db push --accept-data-loss --skip-generate").returncode,
            BLOCK,
        )

    def test_blocks_with_env_prefix(self) -> None:
        self.assertEqual(
            _run("dotenv -e .env -- prisma db push").returncode, BLOCK
        )

    def test_blocks_second_segment(self) -> None:
        # A real push chained after a benign command must still be caught.
        self.assertEqual(
            _run("echo starting && npx prisma db push").returncode, BLOCK
        )

    # --- correct migration workflow: MUST allow --------------------------

    def test_allows_migrate_dev(self) -> None:
        self.assertEqual(_run("prisma migrate dev --name add_users").returncode, ALLOW)

    def test_allows_migrate_deploy(self) -> None:
        self.assertEqual(_run("npx prisma migrate deploy").returncode, ALLOW)

    def test_allows_generate(self) -> None:
        self.assertEqual(_run("prisma generate").returncode, ALLOW)

    # --- prose / mentions must NOT false-trigger -------------------------

    def test_allows_quoted_mention(self) -> None:
        self.assertEqual(
            _run("echo 'never run prisma db push here'").returncode, ALLOW
        )

    def test_allows_comment_mention(self) -> None:
        self.assertEqual(
            _run("echo ok # prisma db push is forbidden").returncode, ALLOW
        )

    def test_allows_git_push(self) -> None:
        # A plain `git push` is unrelated and must pass.
        self.assertEqual(_run("git push origin feature/x").returncode, ALLOW)

    def test_allows_unrelated_db_and_push(self) -> None:
        # `db` and `push` present but not a prisma push.
        self.assertEqual(
            _run("createdb mydb && git push").returncode, ALLOW
        )

    # --- non-Bash tools: MUST allow --------------------------------------

    def test_ignores_non_bash_tools(self) -> None:
        self.assertEqual(_run("prisma db push", tool_name="Read").returncode, ALLOW)


if __name__ == "__main__":
    unittest.main()
