"""Regression tests for ``scripts/block-secret-commit.py``.

This PreToolUse hook blocks a *live credential* (a provider API key, a cloud
access key, a PEM private key) from being introduced into a Bash command, a
tracked file, or a Codex patch — such a value is a bearer credential, and
inlining it leaks a secret into git history / CI / shell history. Like the other
guards it must be precise: fire on a real secret, but stay quiet on placeholders,
connection strings, documentation, and fixtures.

Contract: exit code 2 blocks the tool call; exit code 0 allows it.

Token-shaped literals below are assembled from fragments so this test file never
carries a contiguous secret shape that a scanner (or the guard itself, on an
edit) would flag. The hook receives the fully-joined string at runtime, which is
what matters.

Run with: ``python3 -m unittest tests.block_secret_commit_test``.
"""
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "block-secret-commit.py"

BLOCK = 2
ALLOW = 0

# Fragment-assembled, realistic-looking (mixed letters+digits, no placeholder
# word) live-secret literals — see module docstring.
STRIPE_LIVE = "sk_live_" + "4eC39HqLyjWD" + "arjtT1zdp7dc" + "01ab"
AWS_KEY = "AKIA" + "1234567890" + "ABCDEF"
GITHUB_TOKEN = "ghp_" + "1a2b3c4d5e6f" + "7g8h9i0j1k2l" + "3m4n5o6p7q8r"
GOOGLE_KEY = "AIza" + "Sy" + "A1b2C3d4E5f6" + "G7h8I9j0K1l2" + "M3n4O5p6Q7r"
SLACK_TOKEN = "xoxb-" + "123456789012" + "-abcdefGHIJ1234"
PEM_HEADER = "-----BEGIN RSA PRIVATE" + " KEY-----"

# A documented placeholder the guard must NOT flag (contains "EXAMPLE").
AWS_EXAMPLE = "AKIA" + "IOSFODNN7" + "EXAMPLE"


def _run_payload(payload: dict) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=10,
    )


def _run(tool_name: str, tool_input: dict) -> subprocess.CompletedProcess[str]:
    return _run_payload({"tool_name": tool_name, "tool_input": tool_input})


def _bash(command: str):
    return _run("Bash", {"command": command})


def _write(file_path: str, content: str):
    return _run("Write", {"file_path": file_path, "content": content})


def _edit(file_path: str, new_string: str):
    return _run("Edit", {"file_path": file_path, "new_string": new_string})


class BlockSecretCommitTest(unittest.TestCase):
    # --- blocks real live secrets --------------------------------------------

    def test_blocks_stripe_live_key_in_bash(self) -> None:
        self.assertEqual(_bash(f"export STRIPE_KEY={STRIPE_LIVE}").returncode, BLOCK)

    def test_blocks_aws_access_key_in_bash(self) -> None:
        self.assertEqual(_bash(f"aws configure set x {AWS_KEY}").returncode, BLOCK)

    def test_blocks_github_token_in_write(self) -> None:
        self.assertEqual(_write("config.ts", f'const t = "{GITHUB_TOKEN}"').returncode, BLOCK)

    def test_blocks_google_key_in_write(self) -> None:
        self.assertEqual(_write("config.ts", f'key = "{GOOGLE_KEY}"').returncode, BLOCK)

    def test_blocks_slack_token_in_edit(self) -> None:
        self.assertEqual(_edit("bot.ts", f'token = "{SLACK_TOKEN}"').returncode, BLOCK)

    def test_blocks_pem_private_key_in_write(self) -> None:
        self.assertEqual(_write("id_rsa", f"{PEM_HEADER}\nMIIabc...").returncode, BLOCK)

    def test_blocks_secret_in_multiedit(self) -> None:
        result = _run(
            "MultiEdit",
            {
                "file_path": "app.ts",
                "edits": [
                    {"old_string": "a", "new_string": "b"},
                    {"old_string": "c", "new_string": f'const k = "{STRIPE_LIVE}"'},
                ],
            },
        )
        self.assertEqual(result.returncode, BLOCK)

    def test_blocks_secret_added_in_apply_patch(self) -> None:
        patch = (
            "*** Begin Patch\n"
            "*** Add File: settings.ts\n"
            f"+const key = \"{STRIPE_LIVE}\"\n"
            "*** End Patch\n"
        )
        self.assertEqual(_run("apply_patch", {"command": patch}).returncode, BLOCK)

    def test_blocks_secret_in_cursor_shell_envelope(self) -> None:
        # Cursor beforeShellExecution sends a top-level {command} envelope.
        self.assertEqual(_run_payload({"command": f"echo {STRIPE_LIVE}"}).returncode, BLOCK)

    # --- allows placeholders, non-secrets, and exempt locations --------------

    def test_allows_benign_bash(self) -> None:
        self.assertEqual(_bash("echo hello world").returncode, ALLOW)

    def test_allows_aws_example_placeholder(self) -> None:
        self.assertEqual(_bash(f"aws x {AWS_EXAMPLE}").returncode, ALLOW)

    def test_allows_bare_prefix_without_body(self) -> None:
        # Mentioning a provider prefix (e.g. `git grep sk_live_`) is not a secret.
        self.assertEqual(_bash("git grep sk_live_").returncode, ALLOW)

    def test_allows_connection_string(self) -> None:
        # A DATABASE_URL-style connection string is not a token shape.
        self.assertEqual(
            _write("app.ts", 'DATABASE_URL="postgres://user:pass@db:5432/app"').returncode,
            ALLOW,
        )

    def test_allows_secret_in_example_file(self) -> None:
        self.assertEqual(_write(".env.example", f"KEY={GITHUB_TOKEN}").returncode, ALLOW)

    def test_allows_secret_in_fixture_path(self) -> None:
        self.assertEqual(_write("tests/fixtures/keys.ts", f'k="{STRIPE_LIVE}"').returncode, ALLOW)

    def test_allows_secret_in_documentation(self) -> None:
        self.assertEqual(_write("README.md", f"use `{GITHUB_TOKEN}`").returncode, ALLOW)

    def test_allows_removed_line_in_apply_patch(self) -> None:
        # A secret on a context/removed line (not a `+` addition) is not introduced.
        patch = (
            "*** Begin Patch\n"
            "*** Update File: settings.ts\n"
            f"-const key = \"{STRIPE_LIVE}\"\n"
            "+const key = process.env.STRIPE_KEY\n"
            "*** End Patch\n"
        )
        self.assertEqual(_run("apply_patch", {"command": patch}).returncode, ALLOW)


if __name__ == "__main__":
    unittest.main()
