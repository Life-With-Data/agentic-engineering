"""End-to-end smoke tests for ``scripts/plan-tracker-guard.py``.

The script is the Stop-hook safety net for ``/workflows-plan``. These tests
drive it as a subprocess with fixture transcripts shaped exactly like real
Claude Code transcripts (``record["message"]["content"][i]`` with
``type == "tool_use"`` and ``name`` in {Write, Edit, MultiEdit, NotebookEdit}).

If Anthropic renames the transcript schema, these tests should be the first
thing that breaks — better than the hook silently becoming a no-op.

Run with: ``python3 -m unittest tests.plan_tracker_guard_test``.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = (
    Path(__file__).resolve().parent.parent
    / "scripts"
    / "plan-tracker-guard.py"
)


def _write_transcript(dirpath: Path, tool_uses: list[dict]) -> Path:
    """Build a JSONL transcript with the real Claude Code schema."""
    transcript = dirpath / "transcript.jsonl"
    with transcript.open("w", encoding="utf-8") as fh:
        for tu in tool_uses:
            record = {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "toolu_smoketest",
                            "name": tu["name"],
                            "input": tu["input"],
                        }
                    ],
                },
            }
            fh.write(json.dumps(record) + "\n")
    return transcript


def _run(payload: dict, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=str(cwd),
        timeout=10,
    )


class PlanTrackerGuardTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.cwd = Path(self._tmp.name)
        (self.cwd / "docs" / "plans").mkdir(parents=True)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _make_plan(self, name: str, frontmatter: str) -> Path:
        path = self.cwd / "docs" / "plans" / name
        path.write_text(f"---\n{frontmatter}\n---\n\n# body\n", encoding="utf-8")
        return path

    # ---- core block/pass behavior -----------------------------------------

    def test_blocks_when_frontmatter_lacks_tracker(self) -> None:
        plan = self._make_plan("bad.md", "title: bad\ntype: feat")
        transcript = _write_transcript(
            self.cwd, [{"name": "Write", "input": {"file_path": str(plan)}}]
        )
        result = _run(
            {"transcript_path": str(transcript), "stop_hook_active": False}, self.cwd
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        body = json.loads(result.stdout)
        self.assertEqual(body["decision"], "block")
        self.assertIn("bad.md", body["reason"])
        self.assertIn("github_issue", body["reason"])
        self.assertIn("issue_tracker: none", body["reason"])

    def test_passes_when_github_issue_bare_number_set(self) -> None:
        plan = self._make_plan("good.md", "title: good\ngithub_issue: 42")
        transcript = _write_transcript(
            self.cwd, [{"name": "Edit", "input": {"file_path": str(plan)}}]
        )
        result = _run({"transcript_path": str(transcript)}, self.cwd)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")

    def test_blocks_when_only_bead_id_set(self) -> None:
        # beads is a non-authoritative scratchpad: bead_id is no longer a tracker
        # field, so a plan carrying only bead_id must still block.
        plan = self._make_plan("bead_only.md", "title: b\nbead_id: bd-42")
        transcript = _write_transcript(
            self.cwd, [{"name": "Write", "input": {"file_path": str(plan)}}]
        )
        result = _run({"transcript_path": str(transcript)}, self.cwd)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout)["decision"], "block")

    def test_passes_with_issue_tracker_none_carveout(self) -> None:
        plan = self._make_plan(
            "carveout.md", "title: carved\nissue_tracker: none"
        )
        transcript = _write_transcript(
            self.cwd, [{"name": "Write", "input": {"file_path": str(plan)}}]
        )
        result = _run({"transcript_path": str(transcript)}, self.cwd)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")

    def test_blocks_on_template_placeholders(self) -> None:
        # Template placeholders like "github_issue: NNN" are non-numeric and
        # must not satisfy the tracker requirement.
        plan = self._make_plan(
            "placeholder.md", "title: tpl\ngithub_issue: NNN"
        )
        transcript = _write_transcript(
            self.cwd, [{"name": "Write", "input": {"file_path": str(plan)}}]
        )
        result = _run({"transcript_path": str(transcript)}, self.cwd)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout)["decision"], "block")

    def test_passes_with_crlf_line_endings(self) -> None:
        # A CRLF plan file with a valid github_issue must PASS — the closing
        # fence regex must tolerate the trailing CR (verified false-block).
        path = self.cwd / "docs" / "plans" / "crlf.md"
        path.write_bytes(b"---\r\ntitle: crlf\r\ngithub_issue: 42\r\n---\r\n\r\n# body\r\n")
        transcript = _write_transcript(
            self.cwd, [{"name": "Write", "input": {"file_path": str(path)}}]
        )
        result = _run({"transcript_path": str(transcript)}, self.cwd)
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertEqual(result.stdout, "")

    def test_passes_with_github_issue_with_hash_value(self) -> None:
        plan = self._make_plan(
            "gh.md", "title: gh\ngithub_issue: aagnone3/context#8"
        )
        transcript = _write_transcript(
            self.cwd, [{"name": "Write", "input": {"file_path": str(plan)}}]
        )
        result = _run({"transcript_path": str(transcript)}, self.cwd)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")

    # ---- short-circuit and degraded-input paths ---------------------------

    def test_short_circuits_when_stop_hook_active(self) -> None:
        plan = self._make_plan("bad2.md", "title: bad")
        transcript = _write_transcript(
            self.cwd, [{"name": "Write", "input": {"file_path": str(plan)}}]
        )
        result = _run(
            {"transcript_path": str(transcript), "stop_hook_active": True}, self.cwd
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")

    def test_passes_on_malformed_stdin(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT)],
            input="not json{{{",
            capture_output=True,
            text=True,
            cwd=str(self.cwd),
            timeout=10,
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")

    def test_passes_when_transcript_missing(self) -> None:
        result = _run({"transcript_path": "/nonexistent/path.jsonl"}, self.cwd)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")

    def test_skips_non_plan_files(self) -> None:
        # Tool calls on files outside docs/plans/ must not trigger the hook.
        other = self.cwd / "README.md"
        other.write_text("# readme\n", encoding="utf-8")
        transcript = _write_transcript(
            self.cwd, [{"name": "Write", "input": {"file_path": str(other)}}]
        )
        result = _run({"transcript_path": str(transcript)}, self.cwd)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")

    # ---- security containment --------------------------------------------

    def test_rejects_path_outside_plans_directory(self) -> None:
        # Path matches PLAN_PATH_RE suffix but resolves outside cwd/docs/plans.
        outside = self.cwd.parent / "docs" / "plans" / "elsewhere.md"
        outside.parent.mkdir(parents=True, exist_ok=True)
        outside.write_text("---\ntitle: outside\n---\n", encoding="utf-8")
        transcript = _write_transcript(
            self.cwd, [{"name": "Write", "input": {"file_path": str(outside)}}]
        )
        try:
            result = _run({"transcript_path": str(transcript)}, self.cwd)
            self.assertEqual(result.returncode, 0)
            # Outside paths are silently skipped (stderr-logged), not blocked.
            self.assertEqual(result.stdout, "")
            self.assertIn("unsafe path", result.stderr)
        finally:
            outside.unlink(missing_ok=True)

    def test_rejects_symlinked_plan_file(self) -> None:
        target = self.cwd / "secret.txt"
        target.write_text("not a plan", encoding="utf-8")
        link = self.cwd / "docs" / "plans" / "linked.md"
        try:
            os.symlink(target, link)
        except OSError:
            self.skipTest("symlink unsupported on this platform")
        transcript = _write_transcript(
            self.cwd, [{"name": "Write", "input": {"file_path": str(link)}}]
        )
        result = _run({"transcript_path": str(transcript)}, self.cwd)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertIn("unsafe path", result.stderr)


if __name__ == "__main__":
    unittest.main()
