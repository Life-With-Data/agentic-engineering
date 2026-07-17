"""Cursor `failClosed` allow-contract regression tests for the four safety gates.

Cursor's `beforeShellExecution` / `preToolUse` hooks (wired in
[hooks/hooks-cursor.json](../hooks/hooks-cursor.json) with `failClosed: true`)
require a JSON `{"permission": "allow"}` decision on **stdout** to allow a call.
Under `failClosed: true` an empty stdout is treated as a hook failure and
*blocks* — which previously denied every Shell call because the scripts' allow
path did `sys.exit(0)` with no output. These tests pin the fix: on an allowed
input each gate emits the allow JSON and exits 0.

The same emission is inert on Claude Code (stdout parsed only on exit 0, unknown
fields ignored — `permission` is not in its schema) and Codex (exit-code
contract), so one shared `emit_allow()` covers all three with no branching. The
deny path is unchanged (exit 2 + stderr) and stays covered by each gate's own
`*_test.py`; here we only assert the allow contract.

Run with: ``python3 -m unittest tests.cursor_allow_contract_test``.
"""
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"

# Each gate paired with a payload it must ALLOW. Cursor `beforeShellExecution`
# sends a top-level `{"command": ...}` envelope (no `tool_name`); block-slack
# also runs as a Cursor `preToolUse` Write hook, exercised with its native shape.
ALLOW_CASES = [
    ("block-no-verify.py", {"command": "git commit -m 'normal commit'"}),
    ("prevent-main-commit.py", {"command": "git status"}),
    ("block-db-push.py", {"command": "prisma migrate dev --name init"}),
    ("block-slack-webhook.py", {"command": "echo hello"}),
    (
        "block-slack-webhook.py",
        {"tool_name": "Write", "tool_input": {"file_path": "a.ts", "content": "x"}},
    ),
]


def _run(script: str, payload: dict) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / script)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=10,
    )


class CursorAllowContractTest(unittest.TestCase):
    def test_allow_path_emits_cursor_allow_json_and_exits_zero(self) -> None:
        for script, payload in ALLOW_CASES:
            with self.subTest(script=script, payload=payload):
                result = _run(script, payload)
                self.assertEqual(
                    result.returncode,
                    0,
                    f"{script} should allow this payload (stderr: {result.stderr!r})",
                )
                # failClosed Cursor requires a parseable allow decision on stdout.
                self.assertEqual(
                    json.loads(result.stdout.strip()),
                    {"permission": "allow"},
                    f"{script} allow path must emit Cursor allow JSON, "
                    f"got stdout={result.stdout!r}",
                )


if __name__ == "__main__":
    unittest.main()
