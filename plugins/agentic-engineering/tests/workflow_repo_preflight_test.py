"""Unit tests for workflow-repo-preflight.py's issue-tracker resolution chain.

Chain under test (post unified-lifecycle): local override > committed board
config -> github-project, otherwise "unconfigured" (a state, not a mode — the
repo has not run the wf-setup lifecycle bootstrap). The script filename is
hyphenated, so the module loads via importlib from its path.
"""
from __future__ import annotations

import importlib.util
import inspect
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
        }
        defaults.update(kwargs)
        return preflight.resolve_issue_tracker(**defaults)

    def test_valid_local_override_wins_over_auto_detect(self) -> None:
        # An explicit override reports local.md provenance even where
        # auto-detect would reach the same value.
        _repo_with_config(self.repo, "issue_tracker: github-project")
        info = self._resolve(board_configured=True)
        self.assertEqual(info["resolved"], "github-project")
        self.assertEqual(info["source"], "agentic-engineering.local.md")

    def test_hyphenated_github_project_override_is_accepted(self) -> None:
        # Regression: the pre-lifecycle regex ([A-Za-z]+) silently dropped
        # hyphenated values — `issue_tracker: github-project` must parse.
        _repo_with_config(self.repo, "issue_tracker: github-project")
        info = self._resolve()
        self.assertEqual(info["resolved"], "github-project")
        self.assertEqual(info["local_override"], "github-project")

    def test_invalid_override_falls_through_and_is_surfaced(self) -> None:
        # A stale pin from a retired tracker mode (linear, beads, github,
        # none) must not be silently indistinguishable from "no config at
        # all". "none" retired when unconfigured became a state, not a mode.
        for stale in ("linear", "beads", "github", "none"):
            with self.subTest(stale=stale):
                _repo_with_config(self.repo, f"issue_tracker: {stale}")
                info = self._resolve(board_configured=True)
                self.assertEqual(info["resolved"], "github-project")
                self.assertEqual(info["source"], "auto-detect")
                self.assertIsNone(info["local_override"])
                self.assertEqual(info["local_override_invalid"], stale)

    def test_board_config_resolves_github_project(self) -> None:
        info = self._resolve(board_configured=True)
        self.assertEqual(info["resolved"], "github-project")
        self.assertEqual(info["source"], "auto-detect")

    def test_gh_auth_is_not_a_tracker_signal(self) -> None:
        # gh authentication alone no longer resolves a tracker: without a
        # committed board config the repo is unconfigured, and the resolver
        # takes no gh-auth input at all.
        params = inspect.signature(preflight.resolve_issue_tracker).parameters
        self.assertNotIn("gh_authenticated", params)
        info = self._resolve()
        self.assertEqual(info["resolved"], "unconfigured")

    def test_no_signals_resolves_unconfigured(self) -> None:
        # No override and no board -> the unconfigured *state* (not a mode):
        # gates direct to the wf-setup lifecycle bootstrap.
        info = self._resolve()
        self.assertEqual(info["resolved"], "unconfigured")
        self.assertEqual(info["source"], "auto-detect")
        self.assertIsNone(info["local_override_invalid"])

    def test_missing_config_file_reads_as_no_override(self) -> None:
        valid, invalid = preflight.read_local_config_tracker(self.repo)
        self.assertIsNone(valid)
        self.assertIsNone(invalid)

    def test_tracked_local_config_is_ignored(self) -> None:
        # A .local.md committed to git (would ride a PR) must not pin the
        # tracker — a PR-carried override would steer tracker dispatch for
        # every clone. Mirrors lifecycle_board's read_board_config
        # tracked-file gate. Observable here: the tracked override would
        # claim local.md provenance; ignored, resolution stays unconfigured.
        subprocess.run(["git", "-C", self.repo, "init", "-q"], check=True,
                       capture_output=True, text=True)
        _repo_with_config(self.repo, "issue_tracker: github-project")
        subprocess.run(["git", "-C", self.repo, "add", "agentic-engineering.local.md"],
                       check=True, capture_output=True, text=True)
        info = self._resolve(board_configured=False)
        self.assertEqual(info["resolved"], "unconfigured")
        self.assertEqual(info["source"], "auto-detect")
        self.assertIsNone(info["local_override"])
        self.assertIsNone(info["local_override_invalid"])

    def test_untracked_local_config_in_git_repo_is_honored(self) -> None:
        # The gate keys on *tracked*, not on "a git repo exists": an
        # untracked (gitignored) .local.md is the supported layout and must
        # keep winning over auto-detect.
        subprocess.run(["git", "-C", self.repo, "init", "-q"], check=True,
                       capture_output=True, text=True)
        _repo_with_config(self.repo, "issue_tracker: github-project")
        info = self._resolve(board_configured=False)
        self.assertEqual(info["resolved"], "github-project")
        self.assertEqual(info["source"], "agentic-engineering.local.md")

    def test_github_project_is_the_only_supported_tracker(self) -> None:
        self.assertEqual(preflight.VALID_TRACKERS, {"github-project"})


if __name__ == "__main__":
    unittest.main()
