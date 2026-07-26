"""Unit tests for workflow-repo-preflight.py's issue-tracker resolution chain.

Chain under test (post unified-lifecycle): local override > committed board
config -> github-project, otherwise "unconfigured" (a state, not a mode — the
repo has not run the wf-setup lifecycle bootstrap). The script filename is
hyphenated, so the module loads via importlib from its path.
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

    # --- Parsing matrix (P3-2 regression coverage) ---------------------
    #
    # The old reader used a strict regex anchored to `^\s*key\s*:\s*
    # ([A-Za-z][A-Za-z-]*)\s*$`, so any of the cases below simply failed to
    # match: the value was treated as though the key were entirely absent,
    # with local_override_invalid staying None -- a silent no-op for a user
    # who quoted their value or added a trailing comment. The shared parser
    # (`_load_local_config`) now parses the same flat `key: value` shape
    # config_registry.py's parse_frontmatter uses, so it accepts what
    # config_registry accepts.

    def test_double_quoted_value_parses(self) -> None:
        _repo_with_config(self.repo, 'issue_tracker: "github-project"')
        info = self._resolve(board_configured=False)
        self.assertEqual(info["resolved"], "github-project")
        self.assertEqual(info["source"], "agentic-engineering.local.md")
        self.assertEqual(info["local_override"], "github-project")
        self.assertIsNone(info["local_override_invalid"])

    def test_single_quoted_value_parses(self) -> None:
        _repo_with_config(self.repo, "issue_tracker: 'github-project'")
        info = self._resolve(board_configured=False)
        self.assertEqual(info["resolved"], "github-project")
        self.assertEqual(info["local_override"], "github-project")
        self.assertIsNone(info["local_override_invalid"])

    def test_trailing_comment_is_stripped(self) -> None:
        _repo_with_config(self.repo, "issue_tracker: github-project  # pinned by SRE")
        info = self._resolve(board_configured=False)
        self.assertEqual(info["resolved"], "github-project")
        self.assertIsNone(info["local_override_invalid"])

    def test_quoted_out_of_vocabulary_value_is_reported_invalid(self) -> None:
        # A present-but-unrecognized value must surface as invalid, not
        # silently absent, even when quoted.
        _repo_with_config(self.repo, 'issue_tracker: "linear"')
        info = self._resolve(board_configured=True)
        self.assertIsNone(info["local_override"])
        self.assertEqual(info["local_override_invalid"], "linear")
        self.assertEqual(info["resolved"], "github-project")  # falls back to board config
        self.assertEqual(info["source"], "auto-detect")

    def test_key_absent_from_frontmatter_is_no_override(self) -> None:
        _repo_with_config(self.repo, "some_other_key: value")
        valid, invalid = preflight.read_local_config_tracker(self.repo)
        self.assertIsNone(valid)
        self.assertIsNone(invalid)


class ResolveDeliveryModeTest(unittest.TestCase):
    """delivery_mode's resolution chain mirrors issue_tracker's: local
    override wins; absent one, the resolver falls back to the safe
    `standard` default (there is no board-configured signal to consult)."""

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
        # Mirrors read_local_config_tracker's security invariant: a .local.md
        # tracked in git would ride a PR and pin every clone's delivery mode.
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
    # Mirrors ResolveIssueTrackerTest's matrix above -- both keys share the
    # same reader now, so both must accept what config_registry.py accepts.

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
    """issue_tracker and delivery_mode both live in agentic-engineering.local.md.

    P3-3 was that read_local_config_tracker and read_local_config_delivery_mode
    were ~35-line near-duplicates, each independently running its own `git
    ls-files` check and printing its own near-identical "tracked, ignoring"
    warning -- so a single preflight run against a tracked config printed the
    same warning twice and shelled out to git twice for one fact. These tests
    exercise the shared `_load_local_config` reader both resolvers now go
    through and assert that regression is gone.
    """

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

    def test_tracked_config_warns_once_not_twice_across_both_keys(self) -> None:
        self._init_tracked_config("issue_tracker: github-project\ndelivery_mode: autonomous")

        captured = io.StringIO()
        with contextlib.redirect_stderr(captured):
            preflight.resolve_issue_tracker(repo_root=self.repo, board_configured=False)
            preflight.resolve_delivery_mode(repo_root=self.repo)

        warning_lines = [line for line in captured.getvalue().splitlines() if "is tracked in git" in line]
        self.assertEqual(len(warning_lines), 1, f"expected exactly one tracked-config warning, got: {warning_lines}")

    def test_tracked_config_is_read_once_across_both_keys(self) -> None:
        # The memoized loader must serve the second key's lookup from cache
        # rather than re-running `git ls-files` and re-reading the file.
        self._init_tracked_config("issue_tracker: github-project\ndelivery_mode: autonomous")

        before = preflight._load_local_config.cache_info()
        preflight.resolve_issue_tracker(repo_root=self.repo, board_configured=False)
        after_first = preflight._load_local_config.cache_info()
        preflight.resolve_delivery_mode(repo_root=self.repo)
        after_second = preflight._load_local_config.cache_info()

        self.assertEqual(after_first.misses - before.misses, 1)
        self.assertEqual(after_second.misses - after_first.misses, 0)
        self.assertEqual(after_second.hits - after_first.hits, 1)

    def test_untracked_config_is_read_once_across_both_keys(self) -> None:
        _repo_with_config(self.repo, "issue_tracker: github-project\ndelivery_mode: autonomous")

        before = preflight._load_local_config.cache_info()
        preflight.resolve_issue_tracker(repo_root=self.repo, board_configured=False)
        after_first = preflight._load_local_config.cache_info()
        preflight.resolve_delivery_mode(repo_root=self.repo)
        after_second = preflight._load_local_config.cache_info()

        self.assertEqual(after_first.misses - before.misses, 1)
        self.assertEqual(after_second.misses - after_first.misses, 0)
        self.assertEqual(after_second.hits - after_first.hits, 1)

    def test_present_but_unparsable_value_is_invalid_not_absent(self) -> None:
        # The old per-key regex reader simply failed to match a quoted
        # value, so the invalid slot stayed None -- indistinguishable from
        # "key not set at all". A present value must always resolve to
        # exactly one of (valid, invalid), never silently absent.
        _repo_with_config(self.repo, 'issue_tracker: "linear"')
        valid, invalid = preflight.read_local_config_tracker(self.repo)
        self.assertIsNone(valid)
        self.assertEqual(invalid, "linear")


if __name__ == "__main__":
    unittest.main()
