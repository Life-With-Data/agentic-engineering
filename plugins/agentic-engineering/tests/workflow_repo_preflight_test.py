"""Unit tests for workflow-repo-preflight.py's issue-tracker resolution chain.

The script filename is hyphenated (not importable by name), so the module is
loaded via importlib from its path. ``resolve_issue_tracker`` is pure — all
signals are injected — which is what makes these tests cheap.
"""
from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "workflow-repo-preflight.py"

spec = importlib.util.spec_from_file_location("workflow_repo_preflight", SCRIPT)
assert spec is not None and spec.loader is not None
preflight = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preflight)


def _repo_with_config(tmpdir: str, frontmatter: str | None) -> str:
    if frontmatter is not None:
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
            "beads_initialized": False,
            "beads_installed": False,
            "gh_authenticated": False,
        }
        defaults.update(kwargs)
        return preflight.resolve_issue_tracker(**defaults)

    def test_valid_local_override_wins_over_all_signals(self) -> None:
        _repo_with_config(self.repo, "issue_tracker: github")
        info = self._resolve(beads_initialized=True, beads_installed=True, gh_authenticated=True)
        self.assertEqual(info["resolved"], "github")
        self.assertEqual(info["source"], "agentic-engineering.local.md")
        self.assertEqual(info["local_override"], "github")
        self.assertIsNone(info["local_override_invalid"])

    def test_invalid_override_falls_through_and_is_surfaced(self) -> None:
        # A stale pre-3.0.0 pin must not be silently indistinguishable from
        # "no config at all" — the raw value is surfaced for the caller.
        _repo_with_config(self.repo, "issue_tracker: linear")
        info = self._resolve(gh_authenticated=True)
        self.assertEqual(info["resolved"], "github")
        self.assertEqual(info["source"], "auto-detect")
        self.assertIsNone(info["local_override"])
        self.assertEqual(info["local_override_invalid"], "linear")

    def test_beads_wins_over_authenticated_gh(self) -> None:
        info = self._resolve(beads_initialized=True, beads_installed=True, gh_authenticated=True)
        self.assertEqual(info["resolved"], "beads")
        self.assertEqual(info["source"], "auto-detect")

    def test_beads_requires_both_directory_and_binary(self) -> None:
        info = self._resolve(beads_initialized=True, beads_installed=False, gh_authenticated=True)
        self.assertEqual(info["resolved"], "github")

    def test_gh_only_resolves_github(self) -> None:
        info = self._resolve(gh_authenticated=True)
        self.assertEqual(info["resolved"], "github")
        self.assertEqual(info["source"], "auto-detect")

    def test_no_signals_resolves_none_with_default_source(self) -> None:
        info = self._resolve()
        self.assertEqual(info["resolved"], "none")
        self.assertEqual(info["source"], "default")
        self.assertIsNone(info["local_override_invalid"])

    def test_missing_config_file_reads_as_no_override(self) -> None:
        valid, invalid = preflight.read_local_config_tracker(self.repo)
        self.assertIsNone(valid)
        self.assertIsNone(invalid)

    def test_valid_trackers_no_longer_include_linear(self) -> None:
        self.assertEqual(preflight.VALID_TRACKERS, {"beads", "github", "none"})


if __name__ == "__main__":
    unittest.main()
