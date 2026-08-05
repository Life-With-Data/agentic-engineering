"""Unit tests for workflow-repo-preflight.py's resolution logic.

Issue-tracker resolution is two-state: committed board config ->
github-project, otherwise "unconfigured" (a state, not a mode — the repo has
not run the wf-setup lifecycle bootstrap). delivery_mode still supports a
local-config override. The script filename is hyphenated, so the module loads
via importlib from its path.
"""
from __future__ import annotations

import contextlib
import importlib.util
import inspect
import io
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
    # _load_local_config is memoized per repo_root (fixes P3-3: one read, one
    # git-ls-files check, one warning shared across both keys). Tests that
    # rewrite the same tmpdir's config across subTests/iterations must drop
    # the stale cached parse, or a later write would silently read the first
    # iteration's values back.
    preflight._load_local_config.cache_clear()
    return tmpdir


class ResolveIssueTrackerTest(unittest.TestCase):
    def test_board_config_resolves_github_project(self) -> None:
        info = preflight.resolve_issue_tracker(board_configured=True)
        self.assertEqual(info["resolved"], "github-project")
        self.assertEqual(info["source"], "auto-detect")

    def test_no_board_resolves_unconfigured(self) -> None:
        # No board -> the unconfigured *state* (not a mode): gates direct to
        # the wf-setup lifecycle bootstrap.
        info = preflight.resolve_issue_tracker(board_configured=False)
        self.assertEqual(info["resolved"], "unconfigured")
        self.assertEqual(info["source"], "auto-detect")

    def test_board_config_is_the_only_tracker_signal(self) -> None:
        # gh authentication and local-config overrides are not tracker
        # signals: the resolver takes exactly one input.
        params = inspect.signature(preflight.resolve_issue_tracker).parameters
        self.assertEqual(list(params), ["board_configured"])


class ResolveDeliveryModeTest(unittest.TestCase):
    """delivery_mode's resolution chain: a local override wins; absent one,
    the resolver falls back to the safe `standard` default (there is no
    board-configured signal to consult)."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.repo = self._tmp.name

    def test_valid_local_override_wins_over_default(self) -> None:
        _repo_with_config(self.repo, "delivery_mode: autonomous")
        info = preflight.resolve_delivery_mode(repo_root=self.repo)
        self.assertEqual(info["resolved"], "autonomous")
        self.assertEqual(info["source"], "agentic-engineering.local.md")
        self.assertEqual(info["local_override"], "autonomous")

    def test_invalid_override_falls_through_and_is_surfaced(self) -> None:
        _repo_with_config(self.repo, "delivery_mode: yolo")
        info = preflight.resolve_delivery_mode(repo_root=self.repo)
        self.assertEqual(info["resolved"], "standard")
        self.assertEqual(info["source"], "auto-detect")
        self.assertIsNone(info["local_override"])
        self.assertEqual(info["local_override_invalid"], "yolo")

    def test_no_signals_resolves_standard(self) -> None:
        info = preflight.resolve_delivery_mode(repo_root=self.repo)
        self.assertEqual(info["resolved"], "standard")
        self.assertEqual(info["source"], "auto-detect")
        self.assertIsNone(info["local_override_invalid"])

    def test_missing_config_file_reads_as_no_override(self) -> None:
        valid, invalid = preflight.read_local_config_delivery_mode(self.repo)
        self.assertIsNone(valid)
        self.assertIsNone(invalid)

    def test_tracked_local_config_is_ignored(self) -> None:
        # Security invariant: a .local.md tracked in git would ride a PR and
        # pin every clone's delivery mode.
        subprocess.run(["git", "-C", self.repo, "init", "-q"], check=True,
                       capture_output=True, text=True)
        _repo_with_config(self.repo, "delivery_mode: autonomous")
        subprocess.run(["git", "-C", self.repo, "add", "agentic-engineering.local.md"],
                       check=True, capture_output=True, text=True)
        info = preflight.resolve_delivery_mode(repo_root=self.repo)
        self.assertEqual(info["resolved"], "standard")
        self.assertEqual(info["source"], "auto-detect")
        self.assertIsNone(info["local_override"])

    def test_untracked_local_config_in_git_repo_is_honored(self) -> None:
        subprocess.run(["git", "-C", self.repo, "init", "-q"], check=True,
                       capture_output=True, text=True)
        _repo_with_config(self.repo, "delivery_mode: autonomous")
        info = preflight.resolve_delivery_mode(repo_root=self.repo)
        self.assertEqual(info["resolved"], "autonomous")
        self.assertEqual(info["source"], "agentic-engineering.local.md")

    def test_standard_and_autonomous_are_the_only_supported_modes(self) -> None:
        self.assertEqual(preflight.VALID_DELIVERY_MODES, {"standard", "autonomous"})

    # --- Parsing matrix (P3-2 regression coverage) ----------------------
    # The shared `_load_local_config` reader delegates to
    # lifecycle_board.parse_frontmatter, so it must accept what
    # config_registry.py accepts (quoted values, trailing comments).

    def test_double_quoted_value_parses(self) -> None:
        _repo_with_config(self.repo, 'delivery_mode: "autonomous"')
        info = preflight.resolve_delivery_mode(repo_root=self.repo)
        self.assertEqual(info["resolved"], "autonomous")
        self.assertEqual(info["source"], "agentic-engineering.local.md")
        self.assertEqual(info["local_override"], "autonomous")
        self.assertIsNone(info["local_override_invalid"])

    def test_single_quoted_value_parses(self) -> None:
        _repo_with_config(self.repo, "delivery_mode: 'autonomous'")
        info = preflight.resolve_delivery_mode(repo_root=self.repo)
        self.assertEqual(info["resolved"], "autonomous")
        self.assertEqual(info["local_override"], "autonomous")
        self.assertIsNone(info["local_override_invalid"])

    def test_trailing_comment_is_stripped(self) -> None:
        _repo_with_config(self.repo, "delivery_mode: autonomous  # matches team default")
        info = preflight.resolve_delivery_mode(repo_root=self.repo)
        self.assertEqual(info["resolved"], "autonomous")
        self.assertIsNone(info["local_override_invalid"])

    def test_quoted_out_of_vocabulary_value_is_reported_invalid(self) -> None:
        _repo_with_config(self.repo, 'delivery_mode: "yolo"')
        info = preflight.resolve_delivery_mode(repo_root=self.repo)
        self.assertIsNone(info["local_override"])
        self.assertEqual(info["local_override_invalid"], "yolo")
        self.assertEqual(info["resolved"], "standard")
        self.assertEqual(info["source"], "auto-detect")

    def test_key_absent_from_frontmatter_is_no_override(self) -> None:
        _repo_with_config(self.repo, "some_other_key: value")
        valid, invalid = preflight.read_local_config_delivery_mode(self.repo)
        self.assertIsNone(valid)
        self.assertIsNone(invalid)


class SharedLocalConfigReaderTest(unittest.TestCase):
    """`_load_local_config` is memoized per repo_root: repeated key lookups
    must not re-run `git ls-files`, re-read the file, or re-print the
    "tracked, ignoring" warning."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.repo = self._tmp.name
        preflight._load_local_config.cache_clear()
        self.addCleanup(preflight._load_local_config.cache_clear)

    def _init_tracked_config(self, frontmatter: str) -> None:
        subprocess.run(["git", "-C", self.repo, "init", "-q"], check=True,
                       capture_output=True, text=True)
        _repo_with_config(self.repo, frontmatter)
        subprocess.run(["git", "-C", self.repo, "add", "agentic-engineering.local.md"],
                       check=True, capture_output=True, text=True)

    def test_tracked_config_warns_once_not_twice_across_repeat_reads(self) -> None:
        self._init_tracked_config("delivery_mode: autonomous")

        captured = io.StringIO()
        with contextlib.redirect_stderr(captured):
            preflight.resolve_delivery_mode(repo_root=self.repo)
            preflight.resolve_delivery_mode(repo_root=self.repo)

        warning_lines = [line for line in captured.getvalue().splitlines() if "is tracked in git" in line]
        self.assertEqual(len(warning_lines), 1, f"expected exactly one tracked-config warning, got: {warning_lines}")

    def test_config_is_read_once_across_repeat_reads(self) -> None:
        # The memoized loader must serve the second lookup from cache rather
        # than re-running `git ls-files` and re-reading the file.
        _repo_with_config(self.repo, "delivery_mode: autonomous")

        before = preflight._load_local_config.cache_info()
        preflight.resolve_delivery_mode(repo_root=self.repo)
        after_first = preflight._load_local_config.cache_info()
        preflight.resolve_delivery_mode(repo_root=self.repo)
        after_second = preflight._load_local_config.cache_info()

        self.assertEqual(after_first.misses - before.misses, 1)
        self.assertEqual(after_second.misses - after_first.misses, 0)
        self.assertEqual(after_second.hits - after_first.hits, 1)


if __name__ == "__main__":
    unittest.main()
