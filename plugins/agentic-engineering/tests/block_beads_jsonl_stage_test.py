"""End-to-end smoke tests for ``scripts/block-beads-jsonl-stage.py``.

The script is a PreToolUse/Bash guard that blocks staging the Beads passive
JSONL exports (which ``bd`` regenerates on every mutation). These tests drive
it as a subprocess with the real Claude Code hook payload shape
(``{"tool_name", "tool_input": {"command"}}``).

Contract:
- exit 2 (block) when a ``git add`` names an explicit ``.beads/*.jsonl`` export
- exit 0 (allow) otherwise

If Anthropic renames the hook payload schema, these tests should be the first
thing that breaks — better than the guard silently becoming a no-op.

Run with: ``python3 -m unittest tests.block_beads_jsonl_stage_test``.
"""
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

SCRIPT = (
    Path(__file__).resolve().parent.parent
    / "scripts"
    / "block-beads-jsonl-stage.py"
)


def _run(command: str, tool_name: str = "Bash") -> subprocess.CompletedProcess[str]:
    payload = {"tool_name": tool_name, "tool_input": {"command": command}}
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=10,
    )


class BlockBeadsJsonlStageTest(unittest.TestCase):
    # ---- blocks the footgun ------------------------------------------------

    def test_blocks_plain_add_of_issues_export(self) -> None:
        result = _run("git add .beads/issues.jsonl")
        self.assertEqual(result.returncode, 2, msg=result.stderr)
        self.assertIn("BLOCKED", result.stderr)

    def test_blocks_force_add(self) -> None:
        result = _run("git add -f .beads/issues.jsonl")
        self.assertEqual(result.returncode, 2, msg=result.stderr)

    def test_blocks_interactions_and_events_exports(self) -> None:
        for name in ("interactions", "events"):
            with self.subTest(export=name):
                result = _run(f"git add .beads/{name}.jsonl")
                self.assertEqual(result.returncode, 2, msg=result.stderr)

    def test_blocks_when_export_is_one_of_several_paths(self) -> None:
        result = _run("git add src/foo.ts .beads/issues.jsonl README.md")
        self.assertEqual(result.returncode, 2, msg=result.stderr)

    # ---- allows everything else -------------------------------------------

    def test_allows_unrelated_add(self) -> None:
        result = _run("git add src/foo.ts")
        self.assertEqual(result.returncode, 0, msg=result.stderr)

    def test_allows_add_dash_capital_a(self) -> None:
        # `git add -A` / `git add .` rely on .gitignore to skip the exports.
        self.assertEqual(_run("git add -A").returncode, 0)
        self.assertEqual(_run("git add .").returncode, 0)

    def test_allows_tracked_beads_config(self) -> None:
        result = _run("git add .beads/config.yaml")
        self.assertEqual(result.returncode, 0, msg=result.stderr)

    def test_allows_quoted_prose_mentioning_the_path(self) -> None:
        result = _run('echo "never git add .beads/issues.jsonl"')
        self.assertEqual(result.returncode, 0, msg=result.stderr)

    def test_allows_commented_out_command(self) -> None:
        result = _run("ls  # git add .beads/issues.jsonl")
        self.assertEqual(result.returncode, 0, msg=result.stderr)

    def test_ignores_non_bash_tools(self) -> None:
        result = _run("git add -f .beads/issues.jsonl", tool_name="Write")
        self.assertEqual(result.returncode, 0, msg=result.stderr)


if __name__ == "__main__":
    unittest.main()
