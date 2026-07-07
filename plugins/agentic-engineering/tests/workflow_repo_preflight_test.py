"""Unit tests for workflow-repo-preflight.py's issue-tracker resolution chain.

Chain under test (post unified-lifecycle): local override > committed board
config -> github-project > gh auth -> github > none. The script filename is
hyphenated, so the module loads via importlib from its path.
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "workflow-repo-preflight.py"

spec = importlib.util.spec_from_file_location("workflow_repo_preflight", SCRIPT)
assert spec is not None and spec.loader is not None
preflight = importlib.util.module_from_spec(spec)
sys.modules["workflow_repo_preflight"] = preflight
spec.loader.exec_module(preflight)


def _repo_with_config(tmpdir: str, frontmatter: str) -> str:
    config = Path(tmpdir) / "agentic-engineering.local.md"
    config.write_text(f"---\n{frontmatter}\n---\n\n# Review Context\n", encoding="utf-8")
    return tmpdir


class ResolveIssueTrackerTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.repo = self._tmp.name

    def _resolve(self, **kwargs):
        defaults = {
            "repo_root": self.repo,
            "board_configured": False,
            "gh_authenticated": False,
        }
        defaults.update(kwargs)
        return preflight.resolve_issue_tracker(**defaults)

    def test_valid_local_override_wins_over_all_signals(self) -> None:
        _repo_with_config(self.repo, "issue_tracker: none")
        info = self._resolve(board_configured=True, gh_authenticated=True)
        self.assertEqual(info["resolved"], "none")
        self.assertEqual(info["source"], "agentic-engineering.local.md")

    def test_hyphenated_github_project_override_is_accepted(self) -> None:
        # Regression: the pre-lifecycle regex ([A-Za-z]+) silently dropped
        # hyphenated values — `issue_tracker: github-project` must parse.
        _repo_with_config(self.repo, "issue_tracker: github-project")
        info = self._resolve()
        self.assertEqual(info["resolved"], "github-project")
        self.assertEqual(info["local_override"], "github-project")

    def test_invalid_override_falls_through_and_is_surfaced(self) -> None:
        # A stale pre-3.0.0 pin (linear, beads) must not be silently
        # indistinguishable from "no config at all".
        for stale in ("linear", "beads"):
            with self.subTest(stale=stale):
                _repo_with_config(self.repo, f"issue_tracker: {stale}")
                info = self._resolve(gh_authenticated=True)
                self.assertEqual(info["resolved"], "github")
                self.assertEqual(info["source"], "auto-detect")
                self.assertIsNone(info["local_override"])
                self.assertEqual(info["local_override_invalid"], stale)

    def test_board_config_wins_over_plain_github(self) -> None:
        info = self._resolve(board_configured=True, gh_authenticated=True)
        self.assertEqual(info["resolved"], "github-project")
        self.assertEqual(info["source"], "auto-detect")

    def test_gh_only_resolves_github(self) -> None:
        info = self._resolve(gh_authenticated=True)
        self.assertEqual(info["resolved"], "github")

    def test_no_signals_resolves_none_with_default_source(self) -> None:
        info = self._resolve()
        self.assertEqual(info["resolved"], "none")
        self.assertEqual(info["source"], "default")
        self.assertIsNone(info["local_override_invalid"])

    def test_missing_config_file_reads_as_no_override(self) -> None:
        valid, invalid = preflight.read_local_config_tracker(self.repo)
        self.assertIsNone(valid)
        self.assertIsNone(invalid)

    def test_tracked_local_config_is_ignored(self) -> None:
        # A .local.md committed to git (would ride a PR) must not pin the
        # tracker — `issue_tracker: none` in a PR would bypass board gates.
        # Mirrors lifecycle_board's read_board_config tracked-file gate.
        subprocess.run(["git", "-C", self.repo, "init", "-q"], check=True,
                       capture_output=True, text=True)
        _repo_with_config(self.repo, "issue_tracker: none")
        subprocess.run(["git", "-C", self.repo, "add", "agentic-engineering.local.md"],
                       check=True, capture_output=True, text=True)
        info = self._resolve(board_configured=True, gh_authenticated=True)
        self.assertEqual(info["resolved"], "github-project")
        self.assertEqual(info["source"], "auto-detect")
        self.assertIsNone(info["local_override"])
        self.assertIsNone(info["local_override_invalid"])

    def test_untracked_local_config_in_git_repo_is_honored(self) -> None:
        # The gate keys on *tracked*, not on "a git repo exists": an
        # untracked (gitignored) .local.md is the supported layout and must
        # keep winning over every auto-detect signal.
        subprocess.run(["git", "-C", self.repo, "init", "-q"], check=True,
                       capture_output=True, text=True)
        _repo_with_config(self.repo, "issue_tracker: none")
        info = self._resolve(board_configured=True, gh_authenticated=True)
        self.assertEqual(info["resolved"], "none")
        self.assertEqual(info["source"], "agentic-engineering.local.md")

    def test_valid_trackers_are_the_lifecycle_modes(self) -> None:
        self.assertEqual(preflight.VALID_TRACKERS, {"github-project", "github", "none"})


if __name__ == "__main__":
    unittest.main()
