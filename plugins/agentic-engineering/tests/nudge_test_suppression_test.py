"""Regression tests for ``scripts/nudge-test-suppression.py``.

This PreToolUse hook is a NON-BLOCKING nudge: it never changes the exit code
(always 0) and only emits an advisory ``systemMessage`` on stdout when a command
suppresses test signal (``--passWithNoTests`` and friends) or a file mutation
adds a skipped/focused test to a test file. It must be precise enough that a
benign command, a non-test file, or a documentation mention stays silent.

Contract: exit code is always 0; a non-empty JSON payload on stdout means the
nudge fired.

Run with: ``python3 -m unittest tests.nudge_test_suppression_test``.
"""
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "nudge-test-suppression.py"


def _run(tool_name: str, tool_input: dict) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=json.dumps({"tool_name": tool_name, "tool_input": tool_input}),
        capture_output=True,
        text=True,
        timeout=10,
    )


def _nudged(result: subprocess.CompletedProcess[str]) -> bool:
    """A nudge fired iff exit 0 and stdout carries a systemMessage payload."""
    assert result.returncode == 0, f"hook must never block (exit {result.returncode})"
    out = result.stdout.strip()
    if not out:
        return False
    return "systemMessage" in json.loads(out)


def _bash(command: str):
    return _run("Bash", {"command": command})


def _write(file_path: str, content: str):
    return _run("Write", {"file_path": file_path, "content": content})


class NudgeTestSuppressionTest(unittest.TestCase):
    # --- nudges on suppression -----------------------------------------------

    def test_nudges_pass_with_no_tests(self) -> None:
        self.assertTrue(_nudged(_bash("vitest run --passWithNoTests")))

    def test_nudges_testcontainers_ryuk_disabled(self) -> None:
        self.assertTrue(_nudged(_bash("TESTCONTAINERS_RYUK_DISABLED=true pnpm test")))

    def test_nudges_js_skip_in_test_file(self) -> None:
        self.assertTrue(_nudged(_write("foo.test.ts", 'it.skip("x", () => {})')))

    def test_nudges_js_only_in_spec_file(self) -> None:
        self.assertTrue(_nudged(_write("foo.spec.jsx", 'describe.only("x", () => {})')))

    def test_nudges_xit_in_test_file(self) -> None:
        self.assertTrue(_nudged(_write("a.test.js", 'xit("x", () => {})')))

    def test_nudges_pytest_skip_decorator(self) -> None:
        self.assertTrue(_nudged(_write("test_x.py", "@pytest.mark.skip\ndef test_a():\n    pass")))

    def test_nudges_go_skip(self) -> None:
        self.assertTrue(_nudged(_write("x_test.go", "func TestA(t *testing.T){ t.Skip() }")))

    # --- stays silent on benign / non-test / mentioned cases -----------------

    def test_silent_on_benign_command(self) -> None:
        self.assertFalse(_nudged(_bash("vitest run")))

    def test_silent_on_quoted_flag_mention(self) -> None:
        self.assertFalse(_nudged(_bash('echo "we never use --passWithNoTests"')))

    def test_silent_on_skip_in_non_test_file(self) -> None:
        self.assertFalse(_nudged(_write("helper.ts", 'it.skip("x", () => {})')))

    def test_silent_on_skip_in_documentation(self) -> None:
        self.assertFalse(_nudged(_write("README.md", "avoid it.skip in specs")))

    def test_silent_on_guard_tooling_path(self) -> None:
        # A test-shaped path under scripts/ is the guard's own tooling, exempt.
        self.assertFalse(_nudged(_write("scripts/x.test.ts", 'it.skip("x")')))


if __name__ == "__main__":
    unittest.main()
