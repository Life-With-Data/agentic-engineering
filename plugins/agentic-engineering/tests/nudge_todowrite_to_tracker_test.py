"""Unit tests for nudge-todowrite-to-tracker.py.

Covers: silent when not opted in, silent when a tracker doesn't resolve,
tracker-specific message selection, and the tracked-local-config security
invariant (a git-tracked `agentic-engineering.local.md` must be ignored).
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "nudge-todowrite-to-tracker.py"

spec = importlib.util.spec_from_file_location("nudge_todowrite_to_tracker", SCRIPT)
assert spec is not None and spec.loader is not None
nudge = importlib.util.module_from_spec(spec)
sys.modules["nudge_todowrite_to_tracker"] = nudge
spec.loader.exec_module(nudge)


def _git(repo: str, *args: str) -> None:
    subprocess.run(["git", "-C", repo, *args], check=True, capture_output=True)


def _init_repo(repo: str) -> None:
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")


def _write_config(repo: str, frontmatter: str) -> Path:
    config = Path(repo) / "agentic-engineering.local.md"
    config.write_text(f"---\n{frontmatter}\n---\n\n# Review Context\n", encoding="utf-8")
    return config


class NudgeOptedInTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.repo = self._tmp.name
        _init_repo(self.repo)

    def test_no_config_file_is_not_opted_in(self) -> None:
        self.assertFalse(nudge.nudge_opted_in(self.repo))

    def test_flag_false_is_not_opted_in(self) -> None:
        _write_config(self.repo, "nudge_todowrite: false")
        self.assertFalse(nudge.nudge_opted_in(self.repo))

    def test_flag_absent_is_not_opted_in(self) -> None:
        _write_config(self.repo, "issue_tracker: github")
        self.assertFalse(nudge.nudge_opted_in(self.repo))

    def test_flag_true_is_opted_in(self) -> None:
        _write_config(self.repo, "nudge_todowrite: true")
        self.assertTrue(nudge.nudge_opted_in(self.repo))

    def test_tracked_config_is_ignored(self) -> None:
        # Security invariant shared with issue_tracker/board config reads: a
        # committed copy would ride a PR and silently flip the flag for every
        # clone that pulls it.
        config = _write_config(self.repo, "nudge_todowrite: true")
        _git(self.repo, "add", config.name)
        _git(self.repo, "commit", "-q", "-m", "add tracked local config")
        self.assertFalse(nudge.nudge_opted_in(self.repo))


class ResolveMessageTest(unittest.TestCase):
    """resolve_message() shells out to git/gh assuming cwd == repo root —
    the same convention every sibling hook script relies on, since Claude
    Code invokes hooks with cwd already set to the project directory. Chdir
    into the scratch repo to match that real invocation shape."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.repo = self._tmp.name
        _init_repo(self.repo)
        cwd = os.getcwd()
        self.addCleanup(os.chdir, cwd)
        os.chdir(self.repo)

    def test_none_tracker_yields_no_message(self) -> None:
        # No board config -> resolves to "none", provided gh auth doesn't
        # also signal "github". `shutil.which("gh")` is patched out rather
        # than relied on to return None, because CI runners have `gh`
        # installed and authenticated (GH_TOKEN) — the ambient environment's
        # real gh state must not leak into this assertion.
        with mock.patch.object(nudge.shutil, "which", return_value=None):
            self.assertIsNone(nudge.resolve_message(self.repo))

    def test_github_project_board_config_yields_project_message(self) -> None:
        board_config = Path(self.repo) / "agentic-engineering.md"
        board_config.write_text(
            "---\ngithub_project_owner: aagnone3\ngithub_project_number: 1\n---\n",
            encoding="utf-8",
        )
        _git(self.repo, "remote", "add", "origin", "https://github.com/aagnone3/agentic-engineering.git")
        message = nudge.resolve_message(self.repo)
        self.assertIsNotNone(message)
        self.assertIn("GitHub Project board", message)


class MainNeverBlocksTest(unittest.TestCase):
    """main() must always exit 0 — even when a reused helper raises on
    malformed repo state (e.g. non-UTF-8 bytes in a config file), since this
    hook's entire contract is that a broken nudge must never block TodoWrite."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.repo = self._tmp.name
        _init_repo(self.repo)
        cwd = os.getcwd()
        self.addCleanup(os.chdir, cwd)
        os.chdir(self.repo)

    def _run_hook(self, payload: str) -> "subprocess.CompletedProcess[str]":
        return subprocess.run(
            [sys.executable, str(SCRIPT)], input=payload, text=True, capture_output=True,
        )

    def test_non_utf8_local_config_does_not_crash_the_hook(self) -> None:
        config = Path(self.repo) / "agentic-engineering.local.md"
        config.write_bytes(b"---\nnudge_todowrite: true\n---\n\xff\xfe invalid utf8")
        result = self._run_hook('{"tool_name":"TodoWrite","tool_input":{}}')
        self.assertEqual(result.returncode, 0)

    def test_non_utf8_committed_board_config_does_not_crash_the_hook(self) -> None:
        Path(self.repo, "agentic-engineering.local.md").write_text(
            "---\nnudge_todowrite: true\n---\n", encoding="utf-8")
        board_config = Path(self.repo) / "agentic-engineering.md"
        board_config.write_bytes(b"---\ngithub_project_owner: x\n\xff\xfe---\n")
        result = self._run_hook('{"tool_name":"TodoWrite","tool_input":{}}')
        self.assertEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
