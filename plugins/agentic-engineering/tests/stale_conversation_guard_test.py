"""Tests for ``scripts/stale-conversation-guard.py``.

Pins the load-bearing edges: a fresh conversation is silent, a cold one blocks
exactly once (the re-send is the approval), the threshold is configurable and
disable-able, and every failure mode falls open.

Run with: ``python3 -m unittest tests.stale_conversation_guard_test``.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "stale-conversation-guard.py"

_spec = importlib.util.spec_from_file_location("stale_conversation_guard", SCRIPT)
guard = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(guard)

NOW = datetime(2026, 8, 7, 12, 0, tzinfo=timezone.utc)


def _entry(age_minutes: float) -> str:
    stamp = (NOW - timedelta(minutes=age_minutes)).isoformat().replace("+00:00", "Z")
    return json.dumps({"type": "user", "timestamp": stamp}) + "\n"


def _transcript(tmp: Path, age_minutes: float) -> str:
    """A transcript whose newest entry is `age_minutes` old."""
    path = tmp / "session.jsonl"
    path.write_text(_entry(age_minutes))
    return str(path)


def _append(path: str, age_minutes: float) -> None:
    """A new turn lands on an existing transcript."""
    with open(path, "a") as fh:
        fh.write(_entry(age_minutes))


class EvaluateTest(unittest.TestCase):
    def test_fresh_conversation_is_silent(self):
        with tempfile.TemporaryDirectory() as d:
            block, _ = guard.evaluate(_transcript(Path(d), 5), NOW, 60)
            self.assertFalse(block)

    def test_stale_conversation_blocks_then_resubmit_allows(self):
        with tempfile.TemporaryDirectory() as d:
            path = _transcript(Path(d), 90)
            block, msg = guard.evaluate(path, NOW, 60)
            self.assertTrue(block)
            self.assertIn("90 minutes", msg)
            # Submitting again a moment later is the approval.
            block, _ = guard.evaluate(path, NOW + timedelta(seconds=30), 60)
            self.assertFalse(block)

    def test_ack_survives_a_transcript_that_moves_under_it(self):
        # The transcript is written asynchronously, so a pending entry can flush
        # between the block and the re-submit. A timestamp-keyed ack would
        # desync here and re-block with no way to approve.
        with tempfile.TemporaryDirectory() as d:
            path = _transcript(Path(d), 90)
            self.assertTrue(guard.evaluate(path, NOW, 60)[0])
            _append(path, 89)
            block, _ = guard.evaluate(path, NOW + timedelta(seconds=30), 60)
            self.assertFalse(block)

    def test_ack_expires(self):
        with tempfile.TemporaryDirectory() as d:
            path = _transcript(Path(d), 90)
            self.assertTrue(guard.evaluate(path, NOW, 60)[0])
            later = NOW + timedelta(minutes=guard.ACK_GRACE_MINUTES + 1)
            self.assertTrue(guard.evaluate(path, later, 60)[0])

    def test_guard_rearms_after_new_activity(self):
        with tempfile.TemporaryDirectory() as d:
            path = _transcript(Path(d), 90)
            self.assertTrue(guard.evaluate(path, NOW, 60)[0])
            # The user approves and the conversation resumes...
            _append(path, 0)
            self.assertFalse(guard.evaluate(path, NOW, 60)[0])
            # ...then goes cold again, well past the ack grace window.
            later = NOW + timedelta(minutes=90)
            self.assertTrue(guard.evaluate(path, later, 60)[0])

    def test_ack_file_sits_beside_the_transcript(self):
        with tempfile.TemporaryDirectory() as d:
            path = _transcript(Path(d), 90)
            guard.evaluate(path, NOW, 60)
            self.assertTrue(Path(path + ".stale-ack").exists())

    def test_allow_path_leaves_no_ack(self):
        with tempfile.TemporaryDirectory() as d:
            path = _transcript(Path(d), 5)
            guard.evaluate(path, NOW, 60)
            self.assertFalse(Path(path + ".stale-ack").exists())

    def test_unwritable_ack_fails_open(self):
        with tempfile.TemporaryDirectory() as d:
            path = _transcript(Path(d), 90)
            os.chmod(d, 0o500)
            try:
                self.assertFalse(guard.evaluate(path, NOW, 60)[0])
            finally:
                os.chmod(d, 0o700)

    def test_untimestamped_tail_entries_are_skipped(self):
        # Real transcripts end with `last-prompt` / `custom-title` entries that
        # carry no timestamp; the backward scan must look past them.
        with tempfile.TemporaryDirectory() as d:
            path = _transcript(Path(d), 90)
            with open(path, "a") as fh:
                fh.write(json.dumps({"type": "last-prompt", "prompt": "hi"}) + "\n")
                fh.write(json.dumps({"type": "custom-title"}) + "\n")
            self.assertTrue(guard.evaluate(path, NOW, 60)[0])

    def test_naive_timestamps_are_treated_as_utc(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "session.jsonl"
            naive = (NOW - timedelta(minutes=90)).replace(tzinfo=None).isoformat()
            path.write_text(json.dumps({"timestamp": naive}) + "\n")
            self.assertTrue(guard.evaluate(str(path), NOW, 60)[0])

    def test_age_wording(self):
        self.assertEqual(guard._format_age(90), "90 minutes")
        self.assertEqual(guard._format_age(60 * 5), "5.0 hours")
        self.assertEqual(guard._format_age(60 * 24 * 5), "5.0 days")

    def test_threshold_is_configurable(self):
        with tempfile.TemporaryDirectory() as d:
            path = _transcript(Path(d), 20)
            self.assertFalse(guard.evaluate(path, NOW, 60)[0])
            self.assertTrue(guard.evaluate(path, NOW, 15)[0])

    def test_zero_disables(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertFalse(guard.evaluate(_transcript(Path(d), 600), NOW, 0)[0])

    def test_fails_open(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertFalse(guard.evaluate("", NOW, 60)[0])
            self.assertFalse(guard.evaluate(str(Path(d) / "missing.jsonl"), NOW, 60)[0])
            empty = Path(d) / "empty.jsonl"
            empty.write_text("not json\n{}\n")
            self.assertFalse(guard.evaluate(str(empty), NOW, 60)[0])


class InteractiveTest(unittest.TestCase):
    def test_known_interactive_entrypoints(self):
        for entrypoint in ("cli", "claude-desktop", "vscode", "jetbrains"):
            self.assertTrue(
                guard.is_interactive({"CLAUDE_CODE_ENTRYPOINT": entrypoint}),
                entrypoint,
            )

    def test_automation_never_blocks(self):
        # Unknown / SDK / MCP entrypoints and CI all skip the guard: an erased
        # prompt there is a silent no-op nobody can approve.
        for env in (
            {},
            {"CLAUDE_CODE_ENTRYPOINT": "sdk-ts"},
            {"CLAUDE_CODE_ENTRYPOINT": "sdk-py"},
            {"CLAUDE_CODE_ENTRYPOINT": "mcp"},
            {"CLAUDE_CODE_ENTRYPOINT": "some-future-runner"},
            {"CLAUDE_CODE_ENTRYPOINT": "cli", "CI": "true"},
        ):
            self.assertFalse(guard.is_interactive(env), env)


class EndToEndTest(unittest.TestCase):
    def _run(self, transcript_path, env=None):
        merged = dict(os.environ)
        merged.pop("AGENTIC_STALE_MINUTES", None)
        merged.pop("CI", None)
        merged["CLAUDE_CODE_ENTRYPOINT"] = "cli"
        merged.update(env or {})
        return subprocess.run(
            ["python3", str(SCRIPT)],
            input=json.dumps({"transcript_path": transcript_path, "prompt": "go on"}),
            capture_output=True,
            text=True,
            env=merged,
        )

    def test_stale_transcript_blocks_via_json(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "session.jsonl"
            old = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
            path.write_text(json.dumps({"timestamp": old}) + "\n")
            proc = self._run(str(path))
            # Exit 0 + JSON, NOT exit 2: on this event exit-2 stderr goes to
            # Claude, so the user would never see the explanation.
            self.assertEqual(proc.returncode, 0)
            out = json.loads(proc.stdout)
            self.assertEqual(out["decision"], "block")
            self.assertIn("PAUSED", out["systemMessage"])
            # Submitting again is allowed, and says nothing.
            again = self._run(str(path))
            self.assertEqual(again.returncode, 0)
            self.assertEqual(again.stdout.strip(), "")

    def test_invalid_threshold_falls_back_to_default(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "session.jsonl"
            recent = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
            path.write_text(json.dumps({"timestamp": recent}) + "\n")
            proc = self._run(str(path), {"AGENTIC_STALE_MINUTES": "banana"})
            self.assertEqual(proc.returncode, 0)
            self.assertEqual(proc.stdout.strip(), "")

    def test_disabled_by_env(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "session.jsonl"
            old = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
            path.write_text(json.dumps({"timestamp": old}) + "\n")
            proc = self._run(str(path), {"AGENTIC_STALE_MINUTES": "0"})
            self.assertEqual(proc.returncode, 0)
            self.assertEqual(proc.stderr, "")

    def test_non_interactive_never_blocks(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "session.jsonl"
            old = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
            path.write_text(json.dumps({"timestamp": old}) + "\n")
            proc = self._run(str(path), {"CLAUDE_CODE_ENTRYPOINT": "sdk-ts"})
            self.assertEqual(proc.returncode, 0)
            self.assertEqual(proc.stderr, "")
            # And it leaves no ack behind to confuse a later interactive run.
            self.assertFalse(Path(str(path) + ".stale-ack").exists())


if __name__ == "__main__":
    unittest.main()
